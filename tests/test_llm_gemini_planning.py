"""Phase 12: the Gemini planning path, offline.

What an evaluator can re-run with no key and no network:
  1. the strict plan schema still exists, intact and `strict: true` (OpenAI keeps it verbatim)
  2. the google profile removes *only* `title` keys — same schema, and every `required` key still
     has a property, which is what the endpoint's own validator used to reject
  3. the endpoint profile reaches the wire: an OpenAI endpoint gets the tool byte-identical, a
     Gemini one gets it title-free and greedy
  4. a write step fed by a read step emits `{{dep.latest.field}}` refs, so the model is never asked
     for a payload that does not exist yet, and those refs resolve to the invoice actually found
  5. the LLM path still degrades to the heuristic when anything fails

Measured `finish_reason` per schema variant, and the live transcript behind these claims:
`prompts/phase-12-gemini-planning/REPORT.md`.
"""

from __future__ import annotations

import json
import pathlib
import sys
import types

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))


from src.llm import router as router_mod  # noqa: E402
from src.llm.router import (  # noqa: E402
    GEMINI_MODEL,
    SCHEMA_GOOGLE,
    SCHEMA_STRICT,
    Endpoint,
    LlmError,
    Router,
    _profile_tool,
    _without_titles,
    endpoints,
)
from src.reliability.retry import RetryPolicy  # noqa: E402
from src.runtime.executor import StepResult, resolve_refs  # noqa: E402
from src.runtime.planner import (  # noqa: E402
    PLAN_TOOL_NAME,
    Plan,
    _plan_submit_tool,
    _upstream_args,
    llm_plan,
    make_plan,
)
from src.tools.manifest_registry import execute, registry  # noqa: E402

FAKE_KEY = "AIzaSyD-example_key_material_0123456789"  # shape only, never a real key
TASK = "find the latest invoice for Company X and post it to the ERP"
ONE_KEY = {"GEMINI_API_KEY": FAKE_KEY}


def keys_in(node, key: str) -> int:
    """How many times a key appears anywhere in a schema tree."""
    if isinstance(node, dict):
        return sum(1 for k in node if k == key) + sum(keys_in(v, key) for v in node.values())
    if isinstance(node, list):
        return sum(keys_in(v, key) for v in node)
    return 0


def required_ok(schema: dict) -> bool:
    """Every name in `required` is declared in `properties` — the invariant OpenAPI validators check."""
    return all(name in (schema.get("properties") or {}) for name in schema.get("required") or [])


# --------------------------------------------------------------- 1. strict survives
def test_the_submit_plan_schema_is_still_strict_and_untouched():
    fn = _plan_submit_tool()["function"]
    assert fn["name"] == PLAN_TOOL_NAME and fn["strict"] is True
    # OpenAI still receives the schema with $defs, additionalProperties:false and all keys required.
    assert "$defs" in fn["parameters"] and required_ok(fn["parameters"])
    assert keys_in(fn["parameters"], "additionalProperties") > 0
    assert keys_in(fn["parameters"], "title") > 0, "pydantic emits titles; the profile strips them"


# --------------------------------------------------------------- 2. google profile
def test_the_google_profile_removes_the_titles_and_nothing_else():
    strict_fn = _plan_submit_tool()["function"]
    loose_fn = _without_titles(_plan_submit_tool())["function"]
    assert keys_in(loose_fn["parameters"], "title") == 0
    # strict mode is NOT the thing Gemini rejects, so it stays: nothing is weakened per provider.
    assert loose_fn["strict"] is True
    assert strict_fn["parameters"].keys() - loose_fn["parameters"].keys() == {"title"}
    # $defs/$ref are left exactly as the strict schema has them: Gemini takes them fine.
    assert "Step" in loose_fn["parameters"]["$defs"]
    assert keys_in(loose_fn["parameters"], "$ref") == keys_in(strict_fn["parameters"], "$ref")
    for label, params in (("strict", strict_fn["parameters"]), ("google", loose_fn["parameters"])):
        assert required_ok(params), label
        assert params["properties"]["steps"]["items"] == {"$ref": "#/$defs/Step"}, label
        # the pinned empty args object survives the profile untouched: still {} and still required
        assert params["$defs"]["Step"]["properties"]["args"] == {
            "type": "object", "properties": {}, "required": [], "additionalProperties": False,
            "description": "Leave empty. The planner fills arguments from the tool manifest.",
        }, label


def test_both_schema_variants_are_accepted_by_the_plan_contract():
    """The endpoint's shape differs; what the planner parses must not. A sample tool call parses
    against both, so a Gemini reply and an OpenAI reply reach the same Plan."""
    sample = {"version": 1, "goal": TASK, "steps": [
        {"id": "s1", "tool": "invoice_find_latest", "args": {},
         "depends_on": [], "intent": "find it", "success_criterion": "an invoice comes back"},
        {"id": "s2", "tool": "erp_post_invoice", "args": {}, "depends_on": ["s1"],
         "intent": "post it", "success_criterion": "the ERP takes it"},
    ]}
    blob = json.dumps(sample)
    for mode in (SCHEMA_STRICT, SCHEMA_GOOGLE):
        params = _profile_tool(_plan_submit_tool(), mode)["function"]["parameters"]
        assert required_ok(params), mode
        assert Plan.model_validate_json(blob).goal == TASK


def test_an_unknown_schema_mode_is_a_no_op_not_a_guess():
    assert _profile_tool({"type": "function"}, "something-else") == {"type": "function"}


# --------------------------------------------------------------- 3. the profile reaches the wire
def recording_factory(log: list[dict], out):
    def factory(ep: Endpoint):
        class Fake:
            def __init__(self) -> None:
                self.chat = types.SimpleNamespace(
                    completions=types.SimpleNamespace(create=self._create))

            def _create(self, **kwargs):
                log.append({"key": ep.label, "model": kwargs.get("model"),
                            "tools": kwargs.get("tools"), "temperature": kwargs.get("temperature")})
                return out if not isinstance(out, Exception) else _raise(out)
        return Fake()
    return factory


def _raise(exc):
    raise exc


class Boom(Exception):
    def __init__(self, status: int, message: str = "") -> None:
        self.status_code = status
        super().__init__(message or f"HTTP {status}")


def call_with(env: dict[str, str], log: list[dict], *, out="ok"):
    r = Router(endpoints(env), factory=recording_factory(log, out),
               policy=RetryPolicy(sleeper=lambda _s: None))
    r.chat.completions.create(tools=[_plan_submit_tool()])
    return log[0]


def test_an_openai_endpoint_gets_the_tool_byte_identical():
    log: list[dict] = []
    sent = call_with({"OPENAI_API_KEY": "sk-test-not-a-key"}, log)
    assert sent["tools"][0] == _plan_submit_tool()  # same object: strict OpenAI mode is untouched
    assert sent["temperature"] is None  # and no sampling knob imposed on it


def test_a_gemini_endpoint_gets_the_title_free_schema_and_a_greedy_decode():
    log: list[dict] = []
    sent = call_with(ONE_KEY, log)
    assert keys_in(sent["tools"][0], "title") == 0
    assert sent["tools"][0]["function"]["strict"] is True
    assert sent["model"] == GEMINI_MODEL == "gemma-4-31b-it"  # the default the demo runs on
    assert sent["temperature"] == 0  # sampled decoding planned anywhere from 1 to 5 steps


def test_the_gemini_profile_does_not_touch_the_callers_own_temperature():
    log: list[dict] = []
    r = Router(endpoints(ONE_KEY), factory=recording_factory(log, "ok"),
               policy=RetryPolicy(sleeper=lambda _s: None))
    r.chat.completions.create(tools=[_plan_submit_tool()], temperature=0.7)
    assert log[0]["temperature"] == 0.7


# --------------------------------------------------------------- 4. transient 5xx in place
def test_a_5xx_is_retried_in_place_when_no_other_key_can_take_the_call():
    log: list[dict] = []

    def factory(ep: Endpoint):
        class Fake:
            def __init__(self) -> None:
                self.chat = types.SimpleNamespace(completions=types.SimpleNamespace(create=self._create))

            def _create(self, **kwargs):
                log.append({"key": ep.label})
                if len(log) == 1:
                    raise Boom(500, "Internal error encountered.")
                return {"ok": True}
        return Fake()

    r = Router(endpoints(ONE_KEY), factory=factory, policy=RetryPolicy(sleeper=lambda _s: None))
    assert r.chat.completions.create() == {"ok": True}
    assert [c["key"] for c in log] == ["gemini#1", "gemini#1"]  # same key, asked once more
    assert [e["outcome"] for e in r.events] == ["retry", "ok"]


def test_a_429_is_never_retried_in_place():
    log: list[dict] = []
    r = Router(endpoints(ONE_KEY),
               factory=recording_factory(log, Boom(429, "RESOURCE_EXHAUSTED")),
               policy=RetryPolicy(sleeper=lambda _s: None))
    with pytest.raises(LlmError, match="all 1 LLM key"):
        r.chat.completions.create()
    assert len(log) == 1 and r.cooling("gemini#1") > 0


# --------------------------------------------------------------- 5. fed by a read step
def test_a_write_step_fed_by_a_read_emits_refs_instead_of_invented_values():
    mans = registry()
    find, post = mans["invoice_find_latest"], mans["erp_post_invoice"]
    plan = Plan(goal=TASK, steps=[
        {"id": "s1", "tool": "invoice_find_latest", "intent": "find", "success_criterion": "found"},
        {"id": "s2", "tool": "erp_post_invoice", "intent": "post", "depends_on": ["s1"],
         "success_criterion": "posted"},
    ])
    args = _upstream_args(plan.steps[1], mans)
    assert args["amount"] == "{{s1.latest.amount}}" and args["vendor"] == "{{s1.latest.vendor}}"
    # the two names a record cannot answer, and the enum, come from the manifest instead
    assert args["base_url"] == "" and args["idempotency_key"] == "" and args["action"] == "post"
    assert "{{" in json.dumps(args) and post.risk == "write" and find.risk == "read"


def test_those_refs_resolve_to_the_invoice_that_was_actually_found():
    args = _upstream_args(Plan(goal=TASK, steps=[
        {"id": "s1", "tool": "invoice_find_latest", "intent": "find", "success_criterion": "found"},
        {"id": "s2", "tool": "erp_post_invoice", "depends_on": ["s1"], "intent": "post",
         "success_criterion": "posted"},
    ]).steps[1], registry())
    found = execute("invoice_find_latest", {"company": "Company X", "dir": "seed/invoices",
                                            "pattern": "*"})
    concrete = resolve_refs(args, {"s1": StepResult(step_id="s1", tool="invoice_find_latest",
                                                    status="succeeded", result=found)})
    latest = found["latest"]
    assert concrete["amount"] == latest["amount"] == "4820.00"
    assert concrete["invoice_number"] == latest["invoice_number"] == "CX-2024-0912"
    assert concrete["due_date"] == latest["due"]  # the manifest spells it due_date, the record due
    assert concrete["source_file"] == latest["file"]
    assert not any("{{" in str(v) for v in concrete.values())  # nothing left unresolved


# --------------------------------------------------------------- 6. the llm path, stubbed
def plan_call(goal: str, manifest_prompt: str) -> str:
    return json.dumps({"version": 1, "goal": goal, "steps": [
        {"id": "s1", "tool": "invoice_find_latest", "args": {}, "depends_on": [],
         "intent": "find the latest invoice", "success_criterion": "an invoice comes back"},
        {"id": "s2", "tool": "erp_post_invoice", "args": {}, "depends_on": ["s1"],
         "intent": "post it to the ERP", "success_criterion": "the ERP takes it"},
    ]})


def step_call(tool_name: str, payload: str) -> str:
    return {"invoice_find_latest": json.dumps({"company": "Company X", "dir": "seed/invoices",
                                               "pattern": "*"}),
            "files_list": json.dumps({"dir": "seed/invoices", "pattern": "*"}),
            }.get(tool_name, payload)


class StubLLM:
    """Records every tool call and answers with a fixed plan / a fixed arg set. No socket."""

    def __init__(self, *, fail_on: str = "", answer: str | None = None,
                 plan_json: str | None = None) -> None:
        self.calls: list[list[str]] = []
        self.chat = types.SimpleNamespace(completions=types.SimpleNamespace(create=self._create))
        self._fail_on, self._answer, self._plan_json = fail_on, answer, plan_json

    def _create(self, **kwargs):
        names = [t["function"]["name"] for t in kwargs.get("tools") or []]
        self.calls.append(names)
        if self._fail_on and self._fail_on in names:
            raise Boom(500, "boom")
        if not (kwargs["messages"][-1]["content"] or "").strip():
            raise AssertionError("empty user message")
        args = (self._plan_json if self._plan_json is not None and PLAN_TOOL_NAME in names
                else plan_call(TASK, "") if PLAN_TOOL_NAME in names
                else step_call(names[0], self._answer or ""))
        message = types.SimpleNamespace(tool_calls=[
            types.SimpleNamespace(function=types.SimpleNamespace(name=names[0], arguments=args))])
        return types.SimpleNamespace(choices=[types.SimpleNamespace(message=message)])


def test_a_model_plan_needs_two_calls_not_one_arg_call_per_step():
    stub = StubLLM()
    plan = llm_plan(TASK, registry(), client=stub)
    assert [s.tool for s in plan.topo_order()] == ["invoice_find_latest", "erp_post_invoice"]
    assert stub.calls == [[PLAN_TOOL_NAME], ["invoice_find_latest"]]  # s2 never asked for values
    assert plan.steps[1].args["amount"] == "{{s1.latest.amount}}"


INBOX_TASK = ("list the invoice inbox in seed/invoices and parse INV-X-2024-0703-acme.pdf "
              "and INV-Y-2024-0805-other.txt")


def test_a_read_step_after_a_list_names_its_own_file_instead_of_a_latest_ref():
    # Live failure: qwen planned files_list -> 2x invoice_parse, and both parses died with
    # `unresolved argument reference: 'latest'` — a list result carries no `latest` record.
    # Only a write step takes `{{dep.latest.*}}` refs; a read step is asked for its own file.
    inbox_plan = json.dumps({"version": 1, "goal": INBOX_TASK, "steps": [
        {"id": "s1", "tool": "files_list", "args": {}, "depends_on": [],
         "intent": "list the inbox", "success_criterion": "a listing comes back"},
        {"id": "s2", "tool": "invoice_parse", "args": {}, "depends_on": ["s1"],
         "intent": "parse the pdf", "success_criterion": "fields come back"},
        {"id": "s3", "tool": "invoice_parse", "args": {}, "depends_on": ["s1"],
         "intent": "parse the txt", "success_criterion": "fields come back"},
    ]})
    stub = StubLLM(plan_json=inbox_plan,
                   answer=json.dumps({"path": "seed/invoices/INV-X-2024-0703-acme.pdf"}))
    plan = llm_plan(INBOX_TASK, registry(), client=stub)
    assert stub.calls == [[PLAN_TOOL_NAME], ["files_list"], ["invoice_parse"], ["invoice_parse"]]
    for step in plan.steps[1:]:
        assert step.args["path"].endswith(".pdf") and "{{" not in json.dumps(step.args)


def test_the_plan_source_names_the_model_that_wrote_the_plan(monkeypatch):
    stub = StubLLM()
    client = Router(endpoints(ONE_KEY), factory=lambda ep: stub,
                    policy=RetryPolicy(sleeper=lambda _s: None))
    monkeypatch.setattr(router_mod, "router", lambda *a, **k: client)
    _, source = make_plan(TASK, registry(), client=client)
    assert source == f"llm:gemini/{GEMINI_MODEL}"
    assert client.last_endpoint == f"gemini/{GEMINI_MODEL}"


def test_an_llm_failure_still_degrades_to_the_offline_plan():
    plan, source = make_plan(TASK, registry(), offline=False, client=StubLLM(fail_on=PLAN_TOOL_NAME))
    assert source.startswith("heuristic(fallback:")
    assert [s.tool for s in plan.topo_order()] == ["invoice_find_latest", "erp_post_invoice"]  # unchanged


def test_a_key_echoed_by_the_endpoint_never_rides_out_on_the_fallback_label():
    # The real path: the router scrubs, so the plan source and the run record stay key-free.
    client = Router(endpoints(ONE_KEY),
                    factory=lambda ep: (_ for _ in ()).throw(Boom(500, f"bad key {FAKE_KEY}")),
                    policy=RetryPolicy(sleeper=lambda _s: None))
    _, source = make_plan(TASK, registry(), offline=False, client=client)
    assert source.startswith("heuristic(fallback:") and FAKE_KEY not in source
    assert "[REDACTED]" in source and client.cooling("gemini#1") > 0


def test_offline_is_untouched_by_any_of_this():
    plan, source = make_plan(TASK, registry(), offline=True)
    assert source == "heuristic" and plan.steps[0].args["dir"] == "seed/invoices"