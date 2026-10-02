"""Phase 07: the multi-key LLM router, offline.

Four claims an evaluator can re-run without a key and without a network:
  1. keys are used round-robin, and every key in the environment is picked up (numeric order)
  2. a 429 cools that key and fails over to the next one
  3. a 401 is never retried on the same key, and a 400 is never retried anywhere
  4. no key ever reaches the event log, including inside an upstream error message

Transport is stubbed: no `openai` client is built, no socket is opened, no key is needed.
"""

from __future__ import annotations

import json
import pathlib
import sys
import types

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from src.llm.router import (  # noqa: E402
    GEMINI_BASE_URL,
    GROQ_BASE_URL,
    SCHEMA_GROQ,
    _profile_tool,
    Endpoint,
    LlmError,
    Router,
    endpoints,
    router,
)
from src.reliability.retry import RetryPolicy  # noqa: E402

THREE_KEYS = {"GEMINI_API_KEY": "k-1", "GEMINI_API_KEY_2": "k-2", "GEMINI_API_KEY_3": "k-3"}


class Boom(Exception):
    """What an upstream 429/401/500 looks like to the router: an exception with a status."""

    def __init__(self, status: int, message: str = "") -> None:
        self.status_code = status
        super().__init__(message or f"HTTP {status} from upstream")


def stub_factory(script: dict[str, list], log: list[dict], sleeps: list[float] | None = None):
    """A factory standing in for `openai_client`: records the call, replays the script.

    `script[label]` is a queue of outcomes consumed in order; a default of `{"ok": True}` is
    used once the queue runs dry, so a test only scripts the calls it cares about.
    """
    def factory(ep: Endpoint):
        class Fake:
            def __init__(self) -> None:
                self.chat = types.SimpleNamespace(completions=types.SimpleNamespace(create=self._create))

            def _create(self, **kwargs):
                log.append({"key": ep.label, "model": kwargs.get("model")})
                queue = script.setdefault(ep.label, [{"ok": True}])
                out = queue.pop(0) if len(queue) > 1 else queue[0]
                if isinstance(out, Exception):
                    raise out
                return out

        return Fake()

    return factory


def make_router(env: dict[str, str], script: dict[str, list] | None = None, *,
                log: list[dict] | None = None, sleeps: list[float] | None = None,
                clock=None, cooldown: float = 60.0) -> Router:
    now = clock if clock is not None else types.SimpleNamespace(t=0.0)
    return Router(
        endpoints(env),
        factory=stub_factory(script or {}, log if log is not None else []),
        policy=RetryPolicy(sleeper=sleeps.append if sleeps is not None else (lambda _s: None)),
        clock=(lambda: now.t),
        cooldown=cooldown,
    )


# --- 1. rotation ----------------------------------------------------------
def test_keys_are_read_from_the_environment_in_numeric_order():
    found = endpoints({**THREE_KEYS, "GEMINI_API_KEY_10": "k-10", "GEMINI_API_KEY_ID": "not-a-key",
                       "OPENAI_API_KEY": "openai-1", "OPENAI_API_KEY_2": "openai-2", "GEMINI_API_KEY_": ""})
    assert [ep.label for ep in found] == ["gemini#1", "gemini#2", "gemini#3", "gemini#10",
                                          "openai#1", "openai#2"]
    assert found[0].base_url == GEMINI_BASE_URL and found[0].key == "k-1"
    assert found[-1].base_url is None and found[-1].key == "openai-2"


def test_groq_keys_slot_between_gemini_and_openai():
    found = endpoints({"OPENAI_API_KEY": "o-1", "GROQ_API_KEY": "g-1", "GEMINI_API_KEY": "k-1"})
    assert [ep.label for ep in found] == ["gemini#1", "groq#1", "openai#1"]
    assert found[1].base_url == GROQ_BASE_URL and found[1].key == "g-1"
    log: list[dict] = []
    r = make_router({"GEMINI_API_KEY": "k-1", "GROQ_API_KEY": "g-1"},
                    {"gemini#1": [Boom(503)]}, log=log)
    assert r.chat.completions.create() == {"ok": True}
    assert [c["key"] for c in log] == ["gemini#1", "groq#1"]  # 503 fails over onto groq
    assert found[1].max_tokens == 800 and found[0].max_tokens is None


def test_groq_calls_carry_a_max_tokens_cap_and_gemini_calls_do_not():
    # Measured live: qwen's on-demand tier allows 1000 output tokens/min and answers 429 before
    # asking the model when the estimate hits 1196. The cap rides setdefault: an explicit caller
    # value always wins.
    seen: list[dict] = []

    def factory(ep: Endpoint):
        class Fake:
            def __init__(self) -> None:
                self.chat = types.SimpleNamespace(completions=types.SimpleNamespace(create=self._create))

            def _create(self, **kwargs):
                seen.append({"key": ep.label, "max_tokens": kwargs.get("max_tokens")})
                return {"ok": True}

        return Fake()

    r = Router(endpoints({"GEMINI_API_KEY": "k-1", "GROQ_API_KEY": "g-1"}), factory=factory,
               policy=RetryPolicy(sleeper=lambda _s: None), clock=lambda: 0.0)
    r.chat.completions.create()
    r.chat.completions.create()
    assert [(c["key"], c["max_tokens"]) for c in seen] == [("gemini#1", None), ("groq#1", 800)]


def test_groq_profile_drops_required_where_properties_is_empty():
    # Measured live, three Groq rejections fixed in one profile: `$defs`/`$ref` (the tool never
    # registers), `required` on the pinned-empty `args` (400), `"strict": true` (same refusal as
    # the unregistered tool). The local contract still validates against the untouched schema.
    from src.runtime.planner import _plan_submit_tool  # noqa: E402 - heavy import, this test only

    fn = _profile_tool(_plan_submit_tool(), SCHEMA_GROQ)["function"]
    assert "strict" not in fn
    wired = fn["parameters"]
    blob = json.dumps(wired)
    assert "$defs" not in blob and "$ref" not in blob
    bare: list[str] = []

    def walk(node, path="$"):
        if isinstance(node, dict):
            if "required" in node and not node.get("properties"):
                bare.append(path)
            for k, v in node.items():
                walk(v, f"{path}.{k}")
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, f"{path}[{i}]")

    walk(wired)
    assert bare == []
    step = wired["properties"]["steps"]["items"]["properties"]
    assert step["args"]["properties"] == {}  # still pinned empty: the model still leaves args alone
    assert step["id"] and step["tool"] and step["intent"]  # the step survived the inlining intact


def test_round_robin_spans_every_key_across_calls():
    log: list[dict] = []
    r = make_router(THREE_KEYS, log=log)
    for _ in range(7):
        r.chat.completions.create()
    assert [c["key"] for c in log] == ["gemini#1", "gemini#2", "gemini#3"] * 2 + ["gemini#1"]
    # each endpoint names its own model, because the model id names the provider
    assert {c["model"] for c in log} == {r._endpoints[0].model}


def test_router_is_cached_per_key_set_so_rotation_survives_calls():
    assert router(THREE_KEYS) is router(THREE_KEYS)
    assert router(THREE_KEYS) is not router({"GEMINI_API_KEY": "only"})


# --- 2. 429 failover ------------------------------------------------------
def test_429_cools_the_key_and_fails_over_to_the_next():
    log: list[dict] = []
    sleeps: list[float] = []
    r = make_router(THREE_KEYS, {"gemini#1": [Boom(429, "RESOURCE_EXHAUSTED")], "gemini#2": [{"ok": True}]},
                    log=log, sleeps=sleeps)
    assert r.chat.completions.create() == {"ok": True}
    assert [c["key"] for c in log] == ["gemini#1", "gemini#2"]  # key 1 used once, never twice
    assert r.cooling("gemini#1") > 0 and r.cooling("gemini#2") == 0
    assert sleeps and all(d > 0 for d in sleeps)  # backoff between attempts, never before the first
    assert r.events[0]["outcome"] == "cooldown" and r.events[0]["status"] == 429


def test_5xx_also_fails_over_and_a_key_stays_out_while_it_cools():
    log: list[dict] = []
    clock = types.SimpleNamespace(t=0.0)
    r = make_router(THREE_KEYS, {"gemini#1": [Boom(503)]}, log=log, clock=clock)
    r.chat.completions.create()  # 503 on key 1, so key 2 serves it
    r.chat.completions.create()  # key 1 is cooling: skipped, not tried again
    assert [c["key"] for c in log] == ["gemini#1", "gemini#2", "gemini#2"]
    assert r.cooling("gemini#1") > 0
    clock.t = 1000.0
    assert r.cooling("gemini#1") == 0  # usable again once the cooldown lapses


def test_tool_use_failed_is_retried_in_place_not_failed_over():
    # Measured live on Groq: the byte-identical request serves minutes after a
    # `tool_use_failed` refusal, so the generation flaked, not the request. One same-key retry;
    # a plain bad-schema 400 (no marker) stays fatal, covered by test_400_is_fatal above.
    log: list[dict] = []
    flake = Boom(400, "tool_use_failed: attempted to call tool 'submit_plan' which was not in "
                      "request.tools; failed_generation: {...}")
    r = make_router({"GROQ_API_KEY": "g-1"}, {"groq#1": [flake, {"ok": True}]}, log=log)
    assert r.chat.completions.create() == {"ok": True}
    assert [c["key"] for c in log] == ["groq#1", "groq#1"]  # same key twice, no failover
    assert r.cooling("groq#1") == 0  # a flake does not condemn the key


def test_all_keys_failing_raises_and_names_no_key_material():
    r = make_router(THREE_KEYS, {label: [Boom(429)] for label in ("gemini#1", "gemini#2", "gemini#3")})
    with pytest.raises(LlmError, match="all 3 LLM key"):
        r.chat.completions.create()


def test_no_key_in_the_environment_is_a_plain_error():
    with pytest.raises(LlmError, match="no usable LLM key"):
        make_router({}).chat.completions.create()


# --- 3. never retry a 401 or a 400 ---------------------------------------
def test_401_cools_the_key_and_is_never_retried_on_it():
    log: list[dict] = []
    sleeps: list[float] = []
    r = make_router(THREE_KEYS, {"gemini#1": [Boom(401, "API key not valid")]},
                    log=log, sleeps=sleeps)
    assert r.chat.completions.create() == {"ok": True}
    assert [c["key"] for c in log] == ["gemini#1", "gemini#2"]
    assert [c for c in log if c["key"] == "gemini#1"] == [log[0]]  # exactly one attempt, no retry
    assert r.cooling("gemini#1") > 0 and len(sleeps) == 1  # backed off once, before the next key


def test_400_is_fatal_and_is_not_retried_on_another_key():
    log: list[dict] = []
    r = make_router(THREE_KEYS, {"gemini#1": [Boom(400, "bad tool schema")]}, log=log)
    with pytest.raises(LlmError, match="bad tool schema"):
        r.chat.completions.create()
    assert [c["key"] for c in log] == ["gemini#1"]  # the same request would fail on every key
    assert r.cooling("gemini#1") == 0  # a bad request does not condemn a good key


def test_a_bad_key_reported_as_400_still_fails_over():
    # Captured live: generativelanguage's OpenAI-compatible endpoint answers a dead key with
    # 400 INVALID_ARGUMENT, not 401, so the status alone would strand the run on a dead key.
    log: list[dict] = []
    google_400 = Boom(400, "Error code: 400 - [{'error': {'code': 400, 'message': "
                           "'Please pass a valid API key', 'status': 'INVALID_ARGUMENT'}}]")
    r = make_router(THREE_KEYS, {"gemini#1": [google_400]}, log=log)
    assert r.chat.completions.create() == {"ok": True}
    assert [c["key"] for c in log] == ["gemini#1", "gemini#2"]
    assert r.cooling("gemini#1") > 0


# --- 4. key material never logged ----------------------------------------
FAKE_KEY = "AIzaSyD-9tQ_example_key_material_0123456789"  # shape only, never a real key


def test_key_material_never_reaches_the_event_log():
    log: list[dict] = []
    r = make_router({"GEMINI_API_KEY": FAKE_KEY}, {"gemini#1": [Boom(400, f"invalid key {FAKE_KEY}")]}, log=log)
    with pytest.raises(LlmError):
        r.chat.completions.create()
    blob = json.dumps(r.events)
    assert FAKE_KEY not in blob
    assert "[REDACTED]" in blob  # positive control: the scrub actually fired, it is not a silent pass
    assert repr(r._endpoints[0]).find(FAKE_KEY) == -1  # not in a traceback either


def test_every_error_names_the_key_slot_not_the_key():
    # the only branch needing a private call: a cooled key with no alternative. Waiting out a
    # 60s cooldown would not be a test.
    r = Router(endpoints({"GEMINI_API_KEY": FAKE_KEY}), factory=stub_factory({}, []),
               policy=RetryPolicy(sleeper=lambda _s: None))
    r._cool(r._endpoints[0])
    with pytest.raises(LlmError) as exc:
        r.chat.completions.create()
    assert "cooling down: gemini#1" in str(exc.value) and FAKE_KEY not in str(exc.value)