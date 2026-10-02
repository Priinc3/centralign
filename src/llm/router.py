"""LLM router: rotate N keys across OpenAI-compatible endpoints, fail over on 429/5xx/bad key.

Why this exists: Gemini keys rate-limit per key, so one key means one ceiling. This picks the
next healthy key per call, puts a key that answers 429/5xx — or that the provider rejects as
invalid — into a short cooldown, and never re-sends the same request to a key that already
said no.

Keys come from the environment, in this order:

  GEMINI_API_KEY, GEMINI_API_KEY_2, GEMINI_API_KEY_3, …   (any count, numeric order)
  GROQ_API_KEY, GROQ_API_KEY_2, …                         (fallback: OpenAI-compatible)
  OPENAI_API_KEY, OPENAI_API_KEY_2, …                     (optional fallback endpoints)

Gemini speaks the OpenAI wire format, so this needs no new dependency — the `openai` client
with a different base_url. Refs:
  https://ai.google.dev/gemini-api/docs/openai
  https://ai.google.dev/gemini-api/docs/troubleshooting   (backoff + jitter, transient only)

Endpoints are *profiled*: each one names its own model and its own schema mode, because the same
OpenAI-shaped request is not equally acceptable everywhere. Measured live (phase 12) against
`generativelanguage.googleapis.com/v1beta/openai/`:

  * `title` is the one key Gemini's function-call filter rejects. The planner's strict plan schema
    returns `finish_reason: function_call_filter: MALFORMED_FUNCTION_CALL` with 0 completion tokens;
    deleting only the `title` keys pydantic emits makes the *identical* request return `tool_calls`.
    `strict: true`, `$defs`/`$ref` and `additionalProperties: false` all pass through unharmed, so
    only `title` is stripped. (The *native* endpoint is stricter still and rejects `$defs` and
    `additionalProperties` outright — a native transport would need the whole OpenAPI subset
    rewritten. Not the path taken; the shim is.)
  * the shim answers sporadically `500` on some models, and the request usually works on the same
    key immediately after, so a transient fault gets one in-place retry before the key is cooled.

Three rules the rest of the repo leans on:
  * a key never reaches a log, an event or an exception message (see `_scrub`)
  * a 401/403 — or a 400 that names the key — cools that key and fails over, because a *key*
    fault says nothing about the request
  * every other 4xx is fatal immediately and is never tried on another key: the request is
    bad, so re-sending it only burns quota

Drop-in for an OpenAI client: `router().chat.completions.create(**kw)` is the same call
`src/runtime/planner.py` already makes. Each endpoint names its own model, so the caller's
`model=` is overridden — a GPT model id cannot call Gemini.
"""

from __future__ import annotations

import copy
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Sequence

from ..contracts.events import REDACTED, redact
from ..reliability.retry import RETRYABLE, RetryPolicy, classify

GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemma-4-31b-it")
GROQ_BASE_URL = "https://api.groq.com/openai/v1"
# Measured Oct 2026 on this account: no Llama chat model is served any more (all 404), and
# gpt-oss-120b/20b intermittently refuse their own registered tool (`attempted to call tool
# 'submit_plan' which was not in request.tools` for byte-identical requests that serve minutes
# later). qwen tool-calls cleanly on both planner phases, 7/7 probed. Override per machine.
GROQ_MODEL = os.environ.get("GROQ_MODEL", "qwen/qwen3.8-27b")
# ...and qwen's on-demand tier caps OUTPUT tokens per minute at 1000: without max_tokens Groq
# estimates the completion at 1196 and answers 429 before the model is even asked. A 2-step plan
# is ~350 tokens, step args ~100, so 800 clears both phases with room to spare.
GROQ_MAX_TOKENS = 800
OPENAI_MODEL = os.environ.get("CENTRALIGN_MODEL", "gpt-4.1-mini")
COOLDOWN_S = 60.0
# Per-endpoint schema mode. strict: OpenAI takes the plan schema verbatim; google: the same schema
# minus the keys generativelanguage's function-call filter rejects (see the module docstring).
SCHEMA_STRICT = "strict"
SCHEMA_GOOGLE = "google"
SCHEMA_GROQ = "groq"
# A 429 still only cools the key and moves on — a rate-limited key is not retried in place. 5xx and
# transport faults are the ones that answer differently the moment you ask again (measured).
SAME_KEY_RETRIES = 1
# The key itself is the problem (revoked, wrong project, no access): another key may work.
KEY_FAULT = frozenset({401, 403})
# ...and Google's OpenAI-compatible endpoint answers a bad key with 400 INVALID_ARGUMENT
# ("Please pass a valid API key"), not 401. Without this the whole point of N keys is lost: the
# first dead key would take the run down with it.
KEY_FAULT_TEXT = re.compile(r"api[- _]?key|credential|unauthori[sz]ed|forbidden|permission denied",
                            re.IGNORECASE)
# The request is valid but the serving flaked: Groq validates the model's own tool call server-side
# and its gpt-oss tool parser intermittently refuses a call for a tool that is registered — the
# byte-identical request serves minutes later. `failed_generation` carries the model's (valid)
# output, so this is a dice roll, not a bad request: one in-place retry, same key.
TRANSIENT_TEXT = re.compile(r"tool_use_failed|failed_generation", re.IGNORECASE)


class LlmError(RuntimeError):
    """No usable key, or every key failed. Never carries key material — `_scrub` runs on it."""


@dataclass(frozen=True)
class Endpoint:
    """One key at one base_url. `key` is `repr=False` so no traceback can print it."""

    label: str
    key: str = field(repr=False)
    base_url: str | None = None
    model: str = ""
    schema_mode: str = SCHEMA_STRICT
    max_tokens: int | None = None


def _without_titles(tool: dict[str, Any]) -> dict[str, Any]:
    """The tool exactly as the caller built it, minus every `title` key in its schema.

    Measured (phase 12, `prompts/phase-12-gemini-planning/REPORT.md`): generativelanguage's
    OpenAI-compat endpoint answers the planner's strict plan schema with
    `function_call_filter: MALFORMED_FUNCTION_CALL` and 0 completion tokens, and returns a real
    `tool_calls` step for the same request once the `title` keys are gone. Nothing else is
    touched — `strict`, `$defs`/`$ref`, `additionalProperties: false` and the pinned empty `args`
    object all survive, which is why OpenAI endpoints still get the schema untouched.
    """

    def strip(node: Any) -> None:
        if isinstance(node, dict):
            node.pop("title", None)
            for value in node.values():
                strip(value)
        elif isinstance(node, list):
            for value in node:
                strip(value)

    out = copy.deepcopy(tool)
    strip(out.get("function", {}).get("parameters"))
    return out


def _profile_tool(tool: dict[str, Any], schema_mode: str) -> dict[str, Any]:
    """Per-endpoint wire shape. One mode per provider; the switch is where the next one lands."""
    if schema_mode == SCHEMA_GOOGLE:
        return _without_titles(tool)
    if schema_mode == SCHEMA_GROQ:
        return _for_groq(tool)
    return tool


def _inline_defs(params: dict[str, Any]) -> dict[str, Any]:
    """`$ref: #/$defs/X` pasted in place, `$defs` gone. Groq registers the tool but never
    resolves a ref: with `$defs`/`$ref` in the parameters it answers the model's own call with
    `attempted to call tool 'submit_plan' which was not in request.tools`. The same schema
    with the ref inlined registers, validates, and serves."""

    defs = params.get("$defs", {}) if isinstance(params, dict) else {}

    def inline(node: Any) -> Any:
        if isinstance(node, dict):
            ref = node.get("$ref")
            if set(node.keys()) == {"$ref"} and isinstance(ref, str) and ref.startswith("#/$defs/"):
                target = defs.get(ref.rsplit("/", 1)[-1])
                return inline(copy.deepcopy(target)) if isinstance(target, dict) else node
            return {k: inline(v) for k, v in node.items() if k != "$defs"}
        if isinstance(node, list):
            return [inline(v) for v in node]
        return node

    return inline(params)


def _for_groq(tool: dict[str, Any]) -> dict[str, Any]:
    """Groq's wire shape: no `strict`, no `$ref`, no `required`-without-`properties`.

    Three live-measured rejections, each fixed here and nowhere else (local contract validation
    still runs against the untouched strict schema when the arguments come back):

    1. `$defs`/`$ref` in the parameters: the tool never registers, and the model's own call is
       refused with `attempted to call tool 'submit_plan' which was not in request.tools`. The
       same schema with the ref inlined registers, validates, and serves.
    2. the planner pins `Step.args` to `properties: {}` ("leave every step's args empty"), and
       Groq reads an empty `properties` as a missing one: `'required' present but 'properties'
       is missing`. So `required` is dropped exactly on those nodes.
    3. `"strict": true` on the function: same refusal as (1). The planner validates the
       arguments itself (`Plan.model_validate_json`), so nothing strict was protecting.
    """

    out = copy.deepcopy(tool)
    fn = out.get("function", {})
    fn.pop("strict", None)
    fn["parameters"] = _inline_defs(fn.get("parameters", {}))

    def fix(node: Any) -> None:
        if isinstance(node, dict):
            if "required" in node and not node.get("properties"):
                node.pop("required", None)
            for value in node.values():
                fix(value)
        elif isinstance(node, list):
            for value in node:
                fix(value)

    fix(out.get("function", {}).get("parameters"))
    return out


def _indexed(env: Mapping[str, str], prefix: str) -> list[tuple[int, str]]:
    """`(n, key)` for PREFIX, PREFIX_2, PREFIX_3, … sorted numerically, so _10 lands after _2."""
    out: list[tuple[int, str]] = []
    for name, key in env.items():
        if not key or not name.startswith(prefix):
            continue
        tail = name[len(prefix):]
        digits = tail[1:] if tail.startswith("_") else ""
        if tail and not digits.isdigit():  # GEMINI_API_KEY_ID is not a key slot
            continue
        out.append((int(digits or 1), key))
    return sorted(out)


def endpoints(env: Mapping[str, str] | None = None) -> list[Endpoint]:
    """Every key in the environment, Gemini first, Groq next, OpenAI as the fallback tail."""
    env = os.environ if env is None else env
    out = [Endpoint(label=f"gemini#{n}", key=key, base_url=GEMINI_BASE_URL, model=GEMINI_MODEL,
                    schema_mode=SCHEMA_GOOGLE)
           for n, key in _indexed(env, "GEMINI_API_KEY")]
    out += [Endpoint(label=f"groq#{n}", key=key, base_url=GROQ_BASE_URL, model=GROQ_MODEL,
                     schema_mode=SCHEMA_GROQ, max_tokens=GROQ_MAX_TOKENS)
            for n, key in _indexed(env, "GROQ_API_KEY")]
    out += [Endpoint(label=f"openai#{n}", key=key, base_url=None, model=OPENAI_MODEL)
            for n, key in _indexed(env, "OPENAI_API_KEY")]
    return out


def openai_client(ep: Endpoint) -> Any:
    """The real transport. Optional dep: only the LLM path needs the `openai` package."""
    from openai import OpenAI  # noqa: PLC0415 - keeps this module importable without the SDK

    return OpenAI(api_key=ep.key, base_url=ep.base_url)


def _transport_fault(exc: Exception) -> bool:
    """A connect/timeout error carries no status, and `classify` only reads prose. It counts."""
    try:
        from openai import APIConnectionError, APITimeoutError  # noqa: PLC0415
    except ImportError:
        return False
    return isinstance(exc, (APIConnectionError, APITimeoutError))


class _Completions:
    def __init__(self, router: Router) -> None:
        self._router = router

    def create(self, **kwargs: Any) -> Any:
        return self._router.call(**kwargs)


class _Chat:
    def __init__(self, router: Router) -> None:
        self.completions = _Completions(router)


class Router:
    """Round-robin over healthy keys; one attempt per key per call, then backoff and the next.

    The OpenAI SDK still retries a transport hiccup inside a single call (its own default);
    this layer owns what happens *between* keys: rotation, cooldown, and the fatal triage.
    """

    chat: _Chat

    def __init__(
        self,
        keys: Sequence[Endpoint],
        *,
        factory: Callable[[Endpoint], Any] = openai_client,
        policy: RetryPolicy | None = None,
        clock: Callable[[], float] = time.monotonic,
        cooldown: float = COOLDOWN_S,
    ) -> None:
        self._endpoints = list(keys)
        self._factory = factory
        self._policy = policy or RetryPolicy()
        self._clock = clock
        self._cooldown = cooldown
        self._clients: dict[str, Any] = {}
        self._cool_until: dict[str, float] = {}
        self._cursor = 0
        self.last: Endpoint | None = None
        self.events: list[dict[str, Any]] = []
        self.chat = _Chat(self)

    # ---------------------------------------------------------------- state
    @property
    def last_endpoint(self) -> str:
        """`gemini/gemma-4-31b-it` for the endpoint that served the last call — '' if none did.

        The plan source is only knowable after the call, so this is how a plan earned from the
        wire gets named as a model instead of a shrug of "llm".
        """
        if self.last is None:
            return ""
        return f"{self.last.label.split('#')[0]}/{self.last.model}"

    def cooling(self, label: str) -> float:
        """Seconds left on this key's cooldown — 0 when it is healthy."""
        return max(0.0, self._cool_until.get(label, 0.0) - self._clock())

    def _order(self) -> list[Endpoint]:
        """The healthy keys, each call starting one position further along the configured list.

        The rotation position is over the configured keys, not the healthy ones, so cooling a
        key shifts nothing: it is simply skipped for as long as its cooldown lasts.
        """
        if not self._endpoints:
            return []
        start = self._cursor % len(self._endpoints)
        self._cursor += 1
        return [ep for ep in self._endpoints[start:] + self._endpoints[:start]
                if not self.cooling(ep.label)]

    def _cool(self, ep: Endpoint) -> None:
        self._cool_until[ep.label] = self._clock() + self._cooldown

    def _scrub(self, text: str) -> str:
        """`redact` masks Bearer/sk- shapes; an upstream error that echoes an API key is not
        one of them, so drop every key we hold before the text reaches a log."""
        for ep in self._endpoints:
            if ep.key:
                text = text.replace(ep.key, REDACTED)
        return redact(text)

    def _client(self, ep: Endpoint) -> Any:
        if ep.label not in self._clients:
            self._clients[ep.label] = self._factory(ep)
        return self._clients[ep.label]

    # ----------------------------------------------------------------- call
    def call(self, **kwargs: Any) -> Any:
        """One completion, tried on each healthy key in turn. Raises LlmError if none work.

        `model` is replaced per endpoint, not taken from the caller: the model id names a
        provider, and a GPT model name cannot call Gemini.
        """
        order = self._order()
        if not order:
            found = [ep.label for ep in self._endpoints if self.cooling(ep.label) > 0]
            detail = f" (cooling down: {', '.join(found)})" if found else ""
            raise LlmError(f"no usable LLM key: set GEMINI_API_KEY, GROQ_API_KEY or "
                           f"OPENAI_API_KEY in the environment{detail}")
        last: Exception | None = None
        for attempt, ep in enumerate(order, start=1):
            if attempt > 1:
                self._policy.sleeper(self._policy.delay_for(attempt - 1))
            kwargs["model"] = ep.model  # the endpoint names its provider's model, not the caller
            if ep.max_tokens is not None:  # Groq estimates uncapped output over the OTPM limit
                kwargs.setdefault("max_tokens", ep.max_tokens)
            tools = kwargs.get("tools")
            if tools:  # per-endpoint wire shape; strict mode stays strict on OpenAI
                kwargs["tools"] = [_profile_tool(t, ep.schema_mode) for t in tools]
            if ep.schema_mode != SCHEMA_STRICT:
                # Measured: sampled (the endpoint default) and the same prompt plans anywhere from
                # 1 to 5 steps, including a tool that is not in the manifest. Greedy is a plan, not
                # a dice roll. The caller's own temperature still wins.
                kwargs.setdefault("temperature", 0)
            for retry in range(SAME_KEY_RETRIES + 1):
                try:
                    out = self._client(ep).chat.completions.create(**kwargs)
                except Exception as exc:  # noqa: BLE001 - every transport failure is triage
                    last = exc
                    status = getattr(exc, "status_code", None)
                    reason = self._scrub(str(exc))
                    fault = status in KEY_FAULT or (status == 400 and KEY_FAULT_TEXT.search(reason) is not None)
                    transient = (_transport_fault(exc) or classify(status=status, error=reason) == RETRYABLE
                                 or TRANSIENT_TEXT.search(reason) is not None)
                    if (transient and not fault and status != 429 and retry < SAME_KEY_RETRIES
                            and attempt == len(order)):
                        # A 500 from the compat endpoint is a shrug, not a verdict, and asking the
                        # same key again usually works. Only worth it as the last resort: with
                        # another healthy key the failover is the cheaper retry, so rotation and
                        # "one attempt per key per call" both stay exactly as Phase 07 pinned them.
                        self.events.append({"key": ep.label, "attempt": attempt, "outcome": "retry",
                                            "status": status, "reason": reason})
                        self._policy.sleeper(self._policy.delay_for(retry))
                        continue
                    if fault or transient:
                        self._cool(ep)  # never the same key twice in one call
                        self.events.append({"key": ep.label, "attempt": attempt, "outcome": "cooldown",
                                            "status": status, "reason": reason})
                    else:
                        self.events.append({"key": ep.label, "attempt": attempt, "outcome": "fatal",
                                            "status": status, "reason": reason})
                        raise LlmError(f"{ep.label}: {reason}") from exc
                    break
                self.last = ep
                self.events.append({"key": ep.label, "attempt": attempt, "outcome": "ok"})
                return out
        raise LlmError(f"all {len(order)} LLM key(s) failed, last on {order[-1].label}: "
                       f"{self._scrub(str(last))}") from last


_CACHE: dict[tuple[str, ...], Router] = {}


def router(env: Mapping[str, str] | None = None) -> Router:
    """One router per process per key set — rotation has to span a run's calls, not restart.

    Cached by key labels, so exporting a key mid-process is still picked up.
    """
    keys = endpoints(env)
    names = tuple(ep.label for ep in keys)
    if names not in _CACHE:
        _CACHE[names] = Router(keys)
    return _CACHE[names]