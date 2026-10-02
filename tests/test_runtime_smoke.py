"""Runtime smoke test: fake tools, no LLM key, no network.

Proves the loop itself: DAG dispatch through manifests, idempotent replay,
failing-step isolation, evidence bundle + verdict, secret redaction.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.contracts.events import Event, redact  # noqa: E402
from src.contracts.tools import ToolManifest, validate_args  # noqa: E402
from src.contracts.verdict import Predicate, Verdict  # noqa: E402
from src.ledger.evidence import load_evidence  # noqa: E402
from src.ledger.store import Ledger  # noqa: E402
from src.runtime.executor import Executor, StepResult  # noqa: E402
from src.runtime.loop import demo_callables, demo_manifests, main, run_task  # noqa: E402
from src.runtime.planner import Plan, Step, PlannerError, describe, heuristic_plan, strict_schema  # noqa: E402

CALLS: list[dict] = []


def fake_manifests() -> dict[str, ToolManifest]:
    obj = lambda desc, props, req: {  # noqa: E731 - local shorthand
        "type": "object",
        "properties": props,
        "required": req,
        "additionalProperties": False,
    }
    return {
        "find_invoice": ToolManifest(
            name="find_invoice",
            description="Find the latest invoice for a company",
            parameters=obj("d", {"company": {"type": "string"}, "latest": {"type": "boolean"}}, ["company", "latest"]),
            risk="read",
        ),
        "erp_post": ToolManifest(
            name="erp_post",
            description="Post the invoice into the ERP",
            parameters=obj("d", {"company": {"type": "string"}, "amount": {"type": "number"}}, ["company", "amount"]),
            risk="write",
        ),
        "notify_human": ToolManifest(
            name="notify_human",
            description="Tell the operator the work is done",
            parameters=obj("d", {"text": {"type": "string"}}, ["text"]),
            risk="write",
        ),
        "boom": ToolManifest(
            name="boom",
            description="Always raises, to prove one failure does not kill the run",
            parameters=obj("d", {}, []),
            risk="read",
        ),
        "secret_leak": ToolManifest(
            name="secret_leak",
            description="Returns a credential to prove redaction",
            parameters=obj("d", {}, []),
            risk="read",
        ),
    }


def fake_callables() -> dict:
    def find_invoice(company: str, latest: bool) -> dict:
        CALLS.append({"tool": "find_invoice", "company": company, "latest": latest})
        return {"invoice_id": "inv-7", "company": company, "amount": 1250.5, "due": "2026-11-01"}

    def erp_post(company: str, amount: float) -> dict:
        CALLS.append({"tool": "erp_post", "company": company, "amount": amount})
        return {"erp_id": "erp-42", "posted": amount}

    def notify_human(text: str) -> dict:
        CALLS.append({"tool": "notify_human"})
        return {"notified": True}

    def boom() -> dict:
        raise RuntimeError("tool exploded on purpose")

    def secret_leak() -> dict:
        return {"api_key": "sk-live-DO-NOT-LOG-1234", "note": "ok"}

    return {
        "find_invoice": find_invoice,
        "erp_post": erp_post,
        "notify_human": notify_human,
        "boom": boom,
        "secret_leak": secret_leak,
    }


@pytest.fixture
def tmp_runs(tmp_path: Path) -> Path:
    return tmp_path / "runs"


def test_offline_loop_writes_evidence_with_steps_and_verdict(tmp_runs: Path) -> None:
    CALLS.clear()
    out = run_task(
        'find latest invoice from "Acme Corp", enter into ERP and tell me when done',
        run_root=tmp_runs,
        offline=True,
        manifests=fake_manifests(),
        callables=fake_callables(),
    )
    assert out["status"] == "completed", out
    assert out["verdict"]["status"] == "pass"
    assert out["plan_source"] == "heuristic"

    bundle = load_evidence(out["run_dir"])
    assert bundle["steps"] and bundle["verdict"]["status"] == "pass"
    assert bundle["totals"]["failed"] == 0
    assert sorted(bundle["totals"]["tools_actually_executed"]) == ["erp_post", "find_invoice", "notify_human"]
    assert (Path(out["run_dir"]) / "state.json").is_file()
    assert (Path(out["run_dir"]) / "events.jsonl").is_file()

    # every step in the DAG is in topological order and dependencies came first
    ids = [s["step_id"] for s in bundle["steps"]]
    assert len(ids) == len(set(ids))
    seen: set[str] = set()
    for s in bundle["steps"]:
        assert set(s["depends_on"]) <= seen
        seen.add(s["step_id"])

    # and the args each tool received satisfied the manifest JSON Schema
    manifests = fake_manifests()
    for s in bundle["steps"]:
        assert validate_args(manifests[s["tool"]], s["args"]) == []
    assert {"find_invoice", "erp_post"} <= {c["tool"] for c in CALLS}


def test_second_run_replays_instead_of_re_executing(tmp_runs: Path) -> None:
    manifests, callables = fake_manifests(), fake_callables()
    kwargs = dict(run_root=tmp_runs, offline=True, manifests=manifests, callables=callables)
    first = run_task('find latest invoice from "Acme Corp", enter into ERP and tell me when done', **kwargs)
    assert [s["status"] for s in load_evidence(first["run_dir"])["steps"]].count("succeeded") == 3

    CALLS.clear()
    second = run_task('find latest invoice from "Acme Corp", enter into ERP and tell me when done', **kwargs)
    assert CALLS == [], f"idempotency broken, re-executed: {CALLS}"
    totals = load_evidence(second["run_dir"])["totals"]
    assert [s["status"] for s in load_evidence(second["run_dir"])["steps"]] == ["cached"] * 3
    assert totals["tools_actually_executed"] == [], "nothing ran in this run; do not claim it did"  # F4
    assert totals["tools_replayed"] == ["erp_post", "find_invoice", "notify_human"]


def test_fatal_tool_failure_is_isolated_never_retried_and_verdict_fails(tmp_runs: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    plan = Plan(
        goal="demo failure",
        steps=[
            Step(id="s1", tool="find_invoice", args={"company": "Acme", "latest": True},
                 intent="read", success_criterion="invoice found"),
            Step(id="s2", tool="boom", args={}, depends_on=["s1"], intent="break", success_criterion="never passes"),
            Step(id="s3", tool="notify_human", args={"text": "done"}, depends_on=["s2"],
                 intent="tell human", success_criterion="human told"),
        ],
    )
    monkeypatch.setattr("src.runtime.loop.make_plan", lambda *a, **k: (plan, "test-fixture"))

    out = run_task("demo failure", run_root=tmp_runs, offline=True,
                   manifests=fake_manifests(), callables=fake_callables())
    bundle = load_evidence(out["run_dir"])
    statuses = [s["status"] for s in bundle["steps"]]
    assert statuses == ["succeeded", "failed", "skipped"]
    assert "upstream step(s) ['s2'] did not succeed" in bundle["steps"][2]["error"]
    assert out["status"] == "failed" and out["verdict"]["status"] == "fail"
    assert {p["name"] for p in out["verdict"]["predicates"] if not p["passed"]} == {
        "every_step_resolved", "criterion:s2", "criterion:s3",
    }

    ledger = Ledger(tmp_runs / "_ledger.sqlite3", run_root=tmp_runs)
    rows = ledger.steps_for_run(out["run_id"])
    assert [(r["step_id"], r["attempt"], r["status"]) for r in rows] == [
        ("s1", 1, "succeeded"), ("s2", 1, "failed")  # "exploded on purpose" is unrecognised -> fatal: no retry
    ]
    assert all("tool exploded on purpose" in r["error"] for r in rows if r["step_id"] == "s2")
    assert ledger.count_events(out["run_id"], "step.failed") == 2
    ledger.close()


def test_unknown_tool_and_bad_args_are_never_executed(tmp_runs: Path) -> None:
    ledger = Ledger(tmp_runs / "_ledger.sqlite3", run_root=tmp_runs)
    CALLS.clear()
    ex = Executor(ledger, "run-guard", fake_manifests(), fake_callables())
    ghost = Step(id="s1", tool="rm_rf", args={}, intent="x", success_criterion="x")
    bad = Step(id="s2", tool="erp_post", args={"company": "Acme", "amount": "not-a-number", "sneaky": 1},
               intent="x", success_criterion="x")
    r1 = ex.run_step(ghost, 1)
    r2 = ex.run_step(bad, 2)
    assert r1.status == "skipped" and "not in the manifest registry" in r1.error
    assert r2.status == "skipped" and "manifest schema violation" in r2.error
    assert CALLS == []
    ledger.close()


def test_policy_approval_blocks_before_execution(tmp_runs: Path) -> None:
    ledger = Ledger(tmp_runs / "_ledger.sqlite3", run_root=tmp_runs)
    CALLS.clear()
    ex = Executor(ledger, "run-gate", fake_manifests(), fake_callables(),
                  authorizer=lambda m, a: "approve" if m.risk == "write" else "allow")
    res = ex.run_step(Step(id="s1", tool="erp_post", args={"company": "A", "amount": 1.0},
                           intent="x", success_criterion="x"), 1)
    assert res.status == "skipped" and "approval required" in res.error
    assert CALLS == []
    assert ledger.count_events("run-gate", "approval.requested") == 1
    ledger.close()


def test_secrets_are_never_written_to_the_bundle(tmp_runs: Path) -> None:
    run_task("demo secrets", run_root=tmp_runs, offline=True,
             manifests=fake_manifests(), callables=fake_callables())
    ledger = Ledger(tmp_runs / "_ledger.sqlite3", run_root=tmp_runs)
    ex = Executor(ledger, "run-secret", fake_manifests(), fake_callables())
    ex.run_step(Step(id="s1", tool="secret_leak", args={}, intent="x", success_criterion="x"), 1)
    leaked = ledger.events_for_run("run-secret")[-1]["payload"]
    assert leaked["result"]["api_key"] == "[REDACTED]"
    assert "sk-live-DO-NOT-LOG-1234" not in json.dumps(leaked)
    assert redact("use Bearer abc123def") == "use Bearer [REDACTED]"
    ledger.close()


def test_plan_dag_rejects_cycles_duplicates_and_unknown_deps() -> None:
    with pytest.raises(Exception):
        Plan(goal="g", steps=[Step(id="a", tool="t", depends_on=["b"], intent="i", success_criterion="c"),
                              Step(id="b", tool="t", depends_on=["a"], intent="i", success_criterion="c")])
    with pytest.raises(Exception):
        Plan(goal="g", steps=[Step(id="a", tool="t", depends_on=["zz"], intent="i", success_criterion="c")])
    with pytest.raises(Exception):
        Plan(goal="g", steps=[Step(id="a", tool="t", intent="i", success_criterion="c"),
                              Step(id="a", tool="t", intent="i", success_criterion="c")])
    assert PlannerError is not None


def test_strict_schema_is_openai_compatible() -> None:
    schema = strict_schema(Plan)
    assert schema["additionalProperties"] is False
    assert sorted(schema["required"]) == ["goal", "steps", "version"]
    step = schema["$defs"]["Step"]
    assert step["additionalProperties"] is False
    assert sorted(step["required"]) == ["args", "depends_on", "id", "intent", "success_criterion", "tool"]
    assert demo_manifests()["echo_note"].openai_tool()["function"]["strict"] is True


def test_ledger_uses_wal_and_is_append_only(tmp_runs: Path) -> None:
    path = tmp_runs / "_ledger.sqlite3"
    ledger = Ledger(path, run_root=tmp_runs)
    assert ledger.conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert ledger.conn.execute("PRAGMA busy_timeout").fetchone()[0] == 5000
    ledger.append_event(Event.new("r1", "log", payload={"a": 1}))
    ledger.append_event(Event.new("r1", "log", payload={"a": 2}))
    assert [e["seq"] for e in ledger.events_for_run("r1")] == [0, 1]

    ledger.append_step({"idem_key": "k1", "run_id": "r1", "step_id": "s1", "seq": 1, "tool": "t",
                        "args": {"x": 1}, "status": "succeeded", "result": {"ok": True}})
    # F3: one row per (run, step, attempt) — attempts append, and a re-used attempt number is
    # bumped rather than raising, so a tool failure stays data and never a crash
    ledger.append_step({"idem_key": "k1", "run_id": "r1", "step_id": "s1", "seq": 1, "tool": "t",
                        "args": {"x": 1}, "status": "succeeded", "result": {"ok": True}, "attempt": 1})
    assert [(r["attempt"], r["status"]) for r in ledger.steps_for_run("r1")] == [
        (1, "succeeded"), (2, "succeeded")]
    assert ledger.find_by_idem("k1")["result"] == {"ok": True}
    ledger.close()


def test_offline_planner_fills_args_and_never_calls_network() -> None:
    manifests = fake_manifests()
    plan = heuristic_plan('find latest invoice from "Acme Corp" and enter it into ERP', manifests)
    assert [s.tool for s in plan.topo_order()] == ["find_invoice", "erp_post"]
    assert plan.steps[0].args == {"company": "Acme Corp", "latest": True}
    assert plan.steps[1].depends_on == ["s1"]
    assert all(validate_args(manifests[s.tool], s.args) == [] for s in plan.steps)
    assert demo_callables()["echo_note"]("hi") == {"noted": "hi"}


def test_dotted_names_and_optional_args_stay_strict_compatible() -> None:
    # Phase 02 ships dotted names (erp.post_invoice); OpenAI function names forbid dots.
    m = ToolManifest.model_validate({
        "name": "erp.post_invoice",
        "description": "Post an invoice into the ERP",
        "risk": "write",
        "input_schema": {  # Phase 02's field name; accepted as an alias of `parameters`
            "type": "object",
            "additionalProperties": False,
            "required": ["vendor"],
            "properties": {"vendor": {"type": "string"}, "currency": {"type": "string"}},
        },
    })
    assert m.name == "erp.post_invoice" and m.api_name() == "erp_post_invoice"
    spec = m.openai_tool()["function"]
    assert spec["name"] == "erp_post_invoice" and spec["strict"] is True
    assert sorted(spec["parameters"]["required"]) == ["currency", "vendor"]  # strict: every key required
    assert spec["parameters"]["properties"]["currency"]["type"] == ["string", "null"]  # optional -> nullable
    # internally optional args stay optional for the executor
    assert validate_args(m, {"vendor": "Acme"}) == []
    with pytest.raises(Exception):
        ToolManifest(name="has space", description="x")
    with pytest.raises(Exception):
        ToolManifest(name="x", description="x", parameters={"type": "object", "properties": {"a": {"type": "string"}}})
    assert ToolManifest(name="x", description="x").openai_tool()["function"]["parameters"]["required"] == []


def test_builtin_demo_registry_is_independent_of_siblings(tmp_runs: Path) -> None:
    out = run_task("demo", run_root=tmp_runs, offline=True, tools="demo")
    assert out["status"] == "completed" and out["verdict"]["status"] == "pass"
    assert out["registry"] == "builtin-demo"
    bundle = load_evidence(out["run_dir"])
    assert bundle["totals"]["tools_actually_executed"] == ["echo_note"]
    assert "no tool matched the task" in bundle["steps"][0]["intent"]  # honest about the fallback
    assert [s["step_id"] for s in bundle["steps"]] == ["s1"]


def test_verdict_helpers() -> None:
    v = Verdict.from_predicates("r", [Predicate(name="a", kind="custom", statement="s", passed=True),
                                      Predicate(name="b", kind="custom", statement="s", passed=False)])
    assert v.status == "fail" and [p.name for p in v.failed] == ["b"] and v.ok is False
    assert Verdict.from_predicates("r", [], blocked=True).status == "blocked"
    assert Verdict.from_predicates("r", [Predicate(name="a", kind="custom", statement="s", passed=True)]).ok


# ----------------------------------------------------------------- FIX-1 regressions
def test_ok_false_payload_is_failed_and_never_replayed(tmp_runs: Path) -> None:
    """F2: a tool reports failure in its payload; `{ok: false}` must not read as `succeeded`."""
    ledger = Ledger(tmp_runs / "_ledger.sqlite3", run_root=tmp_runs)
    manifests = {"erp": ToolManifest(name="erp", description="d", risk="write")}
    boom = {"erp": lambda **a: {"ok": False, "status": 422, "error": "amount not a number"}}
    step = lambda: Step(id="s1", tool="erp", args={}, intent="i", success_criterion="c")  # noqa: E731

    first = Executor(ledger, "r1", manifests, boom).run_step(step(), 1)
    assert (first.status, first.ok) == ("failed", False)
    assert first.error == "amount not a number"
    assert ledger.steps_for_run("r1")[0]["status"] == "failed"

    replay = Executor(ledger, "r2", manifests, boom).run_step(step(), 1)
    assert replay.status != "cached" and replay.ok is False, "a failed step replayed as green"
    ledger.close()


def test_executor_resolves_upstream_refs_and_records_concrete_args(tmp_runs: Path) -> None:
    """F1 support: {{s1.latest.amount}} becomes the dependency's value before the schema check."""
    ledger = Ledger(tmp_runs / "_ledger.sqlite3", run_root=tmp_runs)
    manifests = {"post": ToolManifest(
        name="post", description="d",
        parameters={"type": "object", "additionalProperties": False, "required": ["amount"],
                    "properties": {"amount": {"type": "string"}}})}
    seen: list[str] = []

    def post(amount: str) -> dict:
        seen.append(amount)
        return {"ok": True, "amount": amount}

    upstream = StepResult(step_id="s1", tool="find", status="succeeded", result={"latest": {"amount": "4820.00"}})
    step = Step(id="s2", tool="post", args={"amount": "{{s1.latest.amount}}"}, intent="i", success_criterion="c")
    res = Executor(ledger, "r1", manifests, {"post": post}).run_step(step, 2, upstream={"s1": upstream})
    assert res.status == "succeeded" and seen == ["4820.00"]
    assert ledger.steps_for_run("r1")[0]["args"] == {"amount": "4820.00"}  # ledger holds concrete args

    missing = Step(id="s3", tool="post", args={"amount": "{{s1.latest.nope}}"}, intent="i", success_criterion="c")
    res2 = Executor(ledger, "r1", manifests, {"post": post}).run_step(missing, 3, upstream={"s1": upstream})
    assert res2.status == "failed" and "unresolved argument reference" in res2.error
    assert seen == ["4820.00"], "an unresolvable ref must not reach the tool"
    ledger.close()


def test_offline_planner_plans_invoice_intake_find_then_post() -> None:
    """F1: the offline planner plans the reference flow; nothing is mined from the task tail."""
    from src.tools.manifest_registry import registry  # noqa: PLC0415 - sibling registry, planning only

    manifests = registry()
    plan = heuristic_plan("find latest invoice from Company X and post it to the ERP", manifests)
    assert describe(plan) == "s1:invoice_find_latest -> s2:erp_post_invoice"
    find, post = plan.topo_order()
    assert find.args == {"company": "Company X", "dir": "seed/invoices", "pattern": "*.pdf"}
    assert post.depends_on == ["s1"]
    assert post.args["amount"] == "{{s1.latest.amount}}" and post.args["base_url"] == ""
    assert validate_args(manifests[find.tool], find.args) == []
    assert describe(heuristic_plan("find the latest invoice for Company Y and enter it into the ERP", manifests)) \
        == "s1:invoice_find_latest -> s2:erp_post_invoice"


def test_empty_task_blocks_instead_of_passing(tmp_runs: Path) -> None:
    """F3: no goal asked -> no steps, blocked verdict, not a green run."""
    out = run_task("", run_root=tmp_runs, offline=True, tools="demo")
    assert out["verdict"]["status"] == "blocked" and out["verdict"]["summary"] == "No task given"
    assert out["steps"] == [] and out["status"] == "blocked"
    pred = next(p for p in out["verdict"]["predicates"] if p["name"] == "non_empty_goal")
    assert pred["passed"] is False and pred["actual"] is False
    assert main(["--task", "", "--offline", "--tools", "demo", "--runs", str(tmp_runs)]) != 0
