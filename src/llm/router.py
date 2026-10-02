"""LLM router: rotate N keys across OpenAI-compatible endpoints, fail over on 429/5xx/bad key.

Why this exists: Gemini keys rate-limit per key, so one key means one ceiling. This picks the
next healthy key per call, puts a key that answers 429/5xx — or that the provider rejects as
invalid — into a short cooldown, and never re-sends the same request to a key that already
said no.

Keys come from the environment, in this order:

  GEMINI_API_KEY, GEMINI_API_KEY_2, GEMINI_API_KEY_3, …   (any count, numeric order)
  OPENAI_API_KEY, OPENAI_API_KEY_2, …                     (optional fallback endpoints)

Gemini speaks the OpenAI wire format, so this needs no new dependency — the `openai` client
with a different base_url. Refs:
  https://ai.google.dev/gemini-api/docs/openai
  https://ai.google.dev/gemini-api/docs/troubleshooting   (backoff + jitter, transient only)

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

import os
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Sequence

from ..contracts.events import REDACTED, redact
from ..reliability.retry import RETRYABLE, RetryPolicy, classify

GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
OPENAI_MODEL = os.environ.get("CENTRALIGN_MODEL", "gpt-4.1-mini")
COOLDOWN_S = 60.0
# The key itself is the problem (revoked, wrong project, no access): another key may work.
KEY_FAULT = frozenset({401, 403})
# ...and Google's OpenAI-compatible endpoint answers a bad key with 400 INVALID_ARGUMENT
# ("Please pass a valid API key"), not 401. Without this the whole point of N keys is lost: the
# first dead key would take the run down with it.
KEY_FAULT_TEXT = re.compile(r"api[- _]?key|credential|unauthori[sz]ed|forbidden|permission denied",
                            re.IGNORECASE)


class LlmError(RuntimeError):
    """No usable key, or every key failed. Never carries key material — `_scrub` runs on it."""


@dataclass(frozen=True)
class Endpoint:
    """One key at one base_url. `key` is `repr=False` so no traceback can print it."""

    label: str
    key: str = field(repr=False)
    base_url: str | None = None
    model: str = ""


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
    """Every key in the environment, Gemini first, OpenAI as the fallback tail."""
    env = os.environ if env is None else env
    out = [Endpoint(label=f"gemini#{n}", key=key, base_url=GEMINI_BASE_URL, model=GEMINI_MODEL)
           for n, key in _indexed(env, "GEMINI_API_KEY")]
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
        self.events: list[dict[str, Any]] = []
        self.chat = _Chat(self)

    # ---------------------------------------------------------------- state
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
            raise LlmError(f"no usable LLM key: set GEMINI_API_KEY or OPENAI_API_KEY in the "
                           f"environment{detail}")
        last: Exception | None = None
        for attempt, ep in enumerate(order, start=1):
            if attempt > 1:
                self._policy.sleeper(self._policy.delay_for(attempt - 1))
            kwargs["model"] = ep.model  # the endpoint names its provider's model, not the caller
            try:
                out = self._client(ep).chat.completions.create(**kwargs)
            except Exception as exc:  # noqa: BLE001 - every transport failure is triage
                last = exc
                status = getattr(exc, "status_code", None)
                reason = self._scrub(str(exc))
                fault = status in KEY_FAULT or (status == 400 and KEY_FAULT_TEXT.search(reason) is not None)
                transient = _transport_fault(exc) or classify(status=status, error=reason) == RETRYABLE
                if fault or transient:
                    self._cool(ep)  # never the same key twice in one call
                    self.events.append({"key": ep.label, "attempt": attempt, "outcome": "cooldown",
                                        "status": status, "reason": reason})
                    continue
                self.events.append({"key": ep.label, "attempt": attempt, "outcome": "fatal",
                                    "status": status, "reason": reason})
                raise LlmError(f"{ep.label}: {reason}") from exc
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