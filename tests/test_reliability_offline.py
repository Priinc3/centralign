"""Phase 04 reliability, offline: no LLM key, no network, no sim server.

Covers the five named cases (flaky tool recovers on the 3rd try, fatal 422 is never retried,
resume completes, HITL approve releases, empty task blocked) plus the classifier table, the
replan budget, the verifier's fail-closed gate, and the B1 findings this phase carries.

Fake tools only. Real network/sim paths stay in the B2 VERIFY steps.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.contracts.events import Event  # noqa: E402
from src.contracts.tools import ToolManifest  # noqa: E402
from src.ledger.store import Ledger  # noqa: E402
from src.reliability import checkpoint, hitl, replan  # noqa: E402
from src.reliability.retry import (  # noqa: E402
    FATAL,
    RETRYABLE,
    RetryPolicy,
    classify,
    is_retryable,
    run_step_with_retry,
)
from src.runtime.executor import Executor, StepResult  # noqa: E402
from src.runtime.loop import run_task  # noqa: E402
from src.runtime.planner import Plan, Step  # noqa: E402
from src.verifier import checks  # noqa: E402

TIMEOUT_ERR = "TimeoutError: ERP unreachable at http://127.0.0.1:8902/invoices: timed out"
REJECTED_422 = {"ok": False, "status": 422, "error": "missing required field: amount"}


@pytest.fixture
def tmp_runs(tmp_path: Path) -> Path:
    return tmp_path / "runs"


@pytest.fixture
def sleeps() -> list[float]:
    return []


@pytest.fixture
def policy(sleeps: list[float]) -> RetryPolicy:
    """Seeded jitter + a recording sleeper: deterministic delays, no wall-clock waiting."""
    return RetryPolicy(seed=7, sleeper=sleeps.append)


def flaky_manifest() -> ToolManifest:
    return ToolManifest(name="flaky", description="Flaky service that times out before it works", risk="read")


def flaky_step() -> Step:
    return Step(id="s1", tool="flaky", args={}, intent="call the flaky service", success_criterion="it answers")


# ------------------------------------------------------------------ retry / backoff
def test_flaky_tool_succeeds_on_the_third_try_with_growing_backoff(tmp_runs: Path, policy, sleeps) -> None:
    ledger = Ledger(tmp_runs / "_ledger.sqlite3", run_root=tmp_runs)
    calls: list[int] = []

    def flaky() -> dict:
        calls.append(1)
        if len(calls) < 3:
            raise TimeoutError("ERP unreachable at http://127.0.0.1:8902/invoices: timed out")
        return {"ok": True, "posted": 1}

    ex = Executor(ledger, "r1", {"flaky": flaky_manifest()}, {"flaky": flaky})
    res = run_step_with_retry(ex, flaky_step(), 1, policy=policy)

    assert res.status == "succeeded" and res.ok
    assert len(calls) == 3, "must stop at the third attempt, not spin"
    assert len(sleeps) == 2, "one backoff per retry, none for the happy path"
    assert sleeps[1] > sleeps[0], f"backoff must grow: {sleeps}"
    # every attempt is its own append-only ledger row
    assert [(r["attempt"], r["status"]) for r in ledger.steps_for_run("r1")] == [
        (1, "failed"), (2, "failed"), (3, "succeeded"),
    ]
    assert ledger.count_events("r1", "log") == 2, "the retry decision is on the audit trail"
    ledger.close()


def test_fatal_422_is_never_retried(tmp_runs: Path, policy, sleeps) -> None:
    ledger = Ledger(tmp_runs / "_ledger.sqlite3", run_root=tmp_runs)
    calls: list[int] = []

    def rejecting() -> dict:
        calls.append(1)
        return dict(REJECTED_422)

    ex = Executor(ledger, "r1", {"flaky": flaky_manifest()}, {"flaky": rejecting})
    res = run_step_with_retry(ex, flaky_step(), 1, policy=policy)

    assert res.status == "failed" and not res.ok and not res.resolved
    assert len(calls) == 1 and sleeps == [], "a rejected payload earns no second attempt"
    assert len(ledger.steps_for_run("r1")) == 1
    ledger.close()


def test_retries_stop_at_max_attempts(tmp_runs: Path, sleeps) -> None:
    ledger = Ledger(tmp_runs / "_ledger.sqlite3", run_root=tmp_runs)
    ex = Executor(ledger, "r1", {"flaky": flaky_manifest()},
                  {"flaky": lambda: (_ for _ in ()).throw(TimeoutError("timed out"))})
    res = run_step_with_retry(ex, flaky_step(), 1, policy=RetryPolicy(max_attempts=2, seed=1,
                                                                     sleeper=sleeps.append))
    assert res.status == "failed" and len(sleeps) == 1
    assert len(ledger.steps_for_run("r1")) == 2
    ledger.close()


def test_happy_path_never_sleeps(tmp_runs: Path, policy, sleeps) -> None:
    ledger = Ledger(tmp_runs / "_ledger.sqlite3", run_root=tmp_runs)
    ex = Executor(ledger, "r1", {"flaky": flaky_manifest()}, {"flaky": lambda: {"ok": True}})
    res = run_step_with_retry(ex, flaky_step(), 1, policy=policy)
    assert res.status == "succeeded" and sleeps == []
    ledger.close()


@pytest.mark.parametrize(
    ("error", "status", "expected"),
    [
        ("", 422, FATAL),                       # rejected payload
        ("", 429, RETRYABLE),                   # rate limited
        ("", 503, RETRYABLE),                   # server briefly broken
        ("HTTP Error 401: unauthorized", None, FATAL),
        ("HTTP Error 504: gateway timeout", None, RETRYABLE),
        ("", None, FATAL),                      # unrecognised: deny by default
        ("unresolved argument reference: 'nope'", None, FATAL),
        ("manifest schema violation: missing required arg", None, FATAL),
        ("service unavailable", None, RETRYABLE),
        ("connection refused", None, RETRYABLE),
        # an explicit 4xx beats a stray timeout word: the server answered, so resending changes nothing
        ("HTTP Error 422: gateway timeout", None, FATAL),
    ],
)
def test_classify_triage_table(error: str, status: int | None, expected: str) -> None:
    assert classify(error=error, status=status) == expected


def test_is_retryable_only_reads_failed_rows() -> None:
    ok = StepResult(step_id="s1", tool="t", status="succeeded", result={"ok": True})
    skipped = StepResult(step_id="s1", tool="t", status="skipped", error="policy denied this tool")
    fatal = StepResult(step_id="s1", tool="t", status="failed", error="missing required field: amount",
                       result=dict(REJECTED_422))
    flaky = StepResult(step_id="s1", tool="t", status="failed", error=TIMEOUT_ERR)
    assert [is_retryable(r) for r in (ok, skipped, fatal, flaky)] == [False, False, False, True]


def test_delays_are_reproducible_and_bounded() -> None:
    p = RetryPolicy(seed=3)
    assert p.delay_for(1) == p.delay_for(1), "seeded per attempt, not drawn from a shared RNG"
    assert p.delay_for(2) > p.delay_for(1)
    assert 0 < p.delay_for(9) <= RetryPolicy(seed=3).max_delay * (1 + p.jitter / 2)
    assert RetryPolicy(seed=3, jitter=0).delay_for(1) == RetryPolicy(base_delay=0.5, jitter=0).delay_for(1)


# ------------------------------------------------------------------ resume
def test_resume_completes_a_run_the_loop_could_not(tmp_runs: Path) -> None:
    """The wired loop spends 3 policy attempts per plan, and replans once on a transient
    failure, so a service that is out for all 6 calls needs a resume. (Was MAX_ATTEMPTS=2's
    single blind retry before 01's HELP-1.)"""
    manifests, calls = {"flaky": flaky_manifest()}, []

    def flaky() -> dict:
        calls.append(1)
        if len(calls) <= 6:  # out for the sweep's 3 attempts and the replan's 3
            return {"ok": False, "error": "ERP unreachable at http://127.0.0.1:8902/invoices: timed out"}
        return {"ok": True, "posted": 1}

    kwargs = dict(run_root=tmp_runs, offline=True, manifests=manifests, callables={"flaky": flaky})
    first = run_task("run the flaky tool", **kwargs)
    assert first["status"] == "failed" and first["steps"] == ["failed"]
    assert first["plan_source"] == "replan:heuristic" and len(calls) == 6

    second = checkpoint.resume(tmp_runs, first["run_id"], **kwargs)
    assert second["status"] == "completed" and second["verdict"]["status"] == "pass"
    assert second["resumed_from"] == first["run_id"]
    assert len(calls) == 7, "the service is back; the first attempt settles it"

    # a third time is free: the step now replays from the idempotency index
    calls.clear()
    third = checkpoint.resume(tmp_runs, second["run_id"], **kwargs)
    assert third["steps"] == ["cached"] and calls == []
    assert third["inherited"] == {"s1": "succeeded"}


def test_resume_refuses_an_unknown_run(tmp_runs: Path) -> None:
    run_task("demo", run_root=tmp_runs, offline=True, tools="demo")
    with pytest.raises(KeyError):
        checkpoint.resume(tmp_runs, "no-such-run")


def test_checkpoint_round_trips_and_redacts(tmp_runs: Path) -> None:
    run = tmp_runs / "r1"
    checkpoint.save(run, {"stage": "execute", "args": {"api_key": "sk-live-SECRET-1234"}})
    body = checkpoint.load(run)
    assert body["stage"] == "execute" and body["args"]["api_key"] == "[REDACTED]"
    assert "sk-live-SECRET-1234" not in json.dumps(body)
    assert checkpoint.load(tmp_runs / "missing") == {}
    (run / "checkpoint.json").write_text("{truncated", encoding="utf-8")
    assert checkpoint.load(run) == {}, "a torn checkpoint must not block a resume"


# ------------------------------------------------------------------ HITL
def test_approve_closes_the_request_and_releases_the_step(tmp_path: Path) -> None:
    queue = tmp_path / "gate.jsonl"
    manifest = ToolManifest(
        name="erp_post_invoice", description="d", risk="write", requires_approval=True,
        parameters={"type": "object", "additionalProperties": False, "required": ["amount"],
                    "properties": {"amount": {"type": "number"}}},
    )
    ledger = Ledger(tmp_path / "ledger.sqlite3", run_root=tmp_path)
    posted: list[float] = []
    ex = Executor(
        ledger, "r1", {"erp_post_invoice": manifest},
        {"erp_post_invoice": lambda amount: posted.append(amount) or {"ok": True, "amount": amount}},
        authorizer=lambda m, a: hitl.authorizer(m, a, path=queue, threshold=1000.0),
    )
    step = Step(id="s1", tool="erp_post_invoice", args={"amount": 999999.0}, intent="post", success_criterion="posted")

    blocked = ex.run_step(step, 1)
    assert blocked.status == "skipped" and "approval required" in blocked.error
    assert posted == [], "a queued request must never reach the money path"

    waiting = hitl.pending(queue)
    assert len(waiting) == 1 and waiting[0]["tool"] == "erp_post_invoice"
    closed = hitl.decide(waiting[0]["request_id"], approver="alice", path=queue)
    assert closed["verdict"] == hitl.GRANTED and closed["queue"] == hitl.CLOSED
    assert hitl.pending(queue) == [] and hitl.decided(closed["request_id"], queue)

    released = ex.run_step(step, 1, attempt=2)
    assert released.status == "succeeded" and posted == [999999.0]
    assert hitl.pending(queue) == [], "a granted request must not be re-queued"
    ledger.close()


def test_hitl_is_deny_by_default(tmp_path: Path) -> None:
    queue = tmp_path / "gate.jsonl"
    rec = hitl.ensure_request("erp_post_invoice", amount=1e6, risk="write", reason="over limit", path=queue)
    assert rec["queue"] == hitl.PENDING

    with pytest.raises(hitl.ApprovalError):
        hitl.decide("unknown-id", approver="alice", path=queue)      # unknown id is refused
    with pytest.raises(hitl.ApprovalError):
        hitl.decide(rec["request_id"], approver="  ", path=queue)     # an unowned decision is not a decision

    hitl.decide(rec["request_id"], approver="alice", approve=False, reason="wrong vendor", path=queue)
    with pytest.raises(hitl.ApprovalError):
        hitl.decide(rec["request_id"], approver="bob", path=queue)    # already closed
    assert not hitl.decided(rec["request_id"], queue)

    # a denial stays denied: the queue is not re-opened by the next attempt
    again = hitl.ensure_request("erp_post_invoice", amount=1e6, risk="write", path=queue)
    assert again["request_id"] == rec["request_id"] and again["verdict"] == hitl.DENIED


def test_authorizer_only_gates_what_policy_says_it_should(tmp_path: Path) -> None:
    queue = tmp_path / "gate.jsonl"
    write = ToolManifest(name="erp_post_invoice", description="d", risk="write")
    assert hitl.authorizer(write, {"amount": 10.0}, path=queue) == "allow", "under the ceiling"
    assert hitl.authorizer(write, {"amount": 999999.0}, path=queue, threshold=1000.0) == "approve"
    assert hitl.pending(queue)[0]["reason"] == "amount 999999.0 over auto-post 1000.0"
    # the ERP posts amounts as Decimal strings, so a string amount must be read as money too
    assert hitl.authorizer(write, {"amount": "900.00"}, path=queue) == "allow"
    assert hitl.authorizer(write, {"amount": "4,820.00"}, path=queue) == "approve"


def test_hitl_cli_lists_approves_and_refuses(tmp_path: Path, capsys) -> None:
    queue = str(tmp_path / "gate.jsonl")
    rid = hitl.ensure_request("erp_post_invoice", amount=999999.0, path=queue)["request_id"]

    assert hitl.main(["--pending", "--queue", queue]) == 0
    assert rid in capsys.readouterr().out, "the pending list must name the id a human approves"

    assert hitl.main(["--approve", rid, "--approver", "alice", "--queue", queue]) == 0
    assert hitl.decided(rid, queue)
    assert hitl.main(["--approve", rid, "--approver", "bob", "--queue", queue]) == 2  # already closed
    with pytest.raises(SystemExit):
        hitl.main(["--queue", queue])  # no subcommand is a usage error


# ------------------------------------------------------------------ verifier
def _ledger_with_started(run_id: str, tmp_runs: Path) -> Ledger:
    """A ledger holding exactly one `run.started` — `audit_trail_complete` requires exactly one."""
    ledger = Ledger(tmp_runs / "_ledger.sqlite3", run_root=tmp_runs)
    ledger.append_event(Event.new(run_id, "run.started", payload={"task": "demo"}))
    return ledger


def test_verifier_fails_closed_on_a_success_with_no_evidence(tmp_runs: Path) -> None:
    ledger = _ledger_with_started("r1", tmp_runs)
    plan = Plan(goal="demo", steps=[Step(id="s1", tool="flaky", intent="i", success_criterion="it answers")])
    lied = StepResult(step_id="s1", tool="flaky", status="succeeded", result={"ok": False, "status": 500})

    verdict = checks.verify({"run_id": "r1", "task": "demo"}, plan, [lied], ledger)

    assert verdict.status == "fail"
    assert {"each_success_has_evidence", "criterion:s1"} <= {p.name for p in verdict.failed}
    ledger.close()


def test_verifier_emits_the_contracted_predicates_for_a_clean_run(tmp_runs: Path) -> None:
    ledger = _ledger_with_started("r2", tmp_runs)
    ledger.append_event(Event.new("r2", "step.succeeded", step_id="s1", tool="flaky"))
    plan = Plan(goal="demo", steps=[Step(id="s1", tool="flaky", intent="i", success_criterion="it answers")])
    good = StepResult(step_id="s1", tool="flaky", status="succeeded", result={"ok": True, "posted": 1})

    verdict = checks.verify({"run_id": "r2", "task": "demo"}, plan, [good], ledger)

    assert [p.name for p in verdict.predicates] == [
        "non_empty_goal", "plan_has_steps", "every_step_resolved", "no_silent_skips",
        "each_success_has_evidence", "audit_trail_complete", "criterion:s1",
    ]
    assert verdict.status == "pass" and verdict.ok
    assert next(p for p in verdict.predicates if p.name == "audit_trail_complete").actual == 2
    ledger.close()


def test_verifier_counts_cached_steps_as_verified_evidence(tmp_runs: Path) -> None:
    """The bug this replaces: expected/actual were computed from different status sets, so an
    all-cached run reported `expected: 0, actual: 0` for each_success_has_evidence."""
    ledger = _ledger_with_started("r3", tmp_runs)
    ledger.append_event(Event.new("r3", "step.cached", step_id="s1", tool="flaky"))
    plan = Plan(goal="demo", steps=[Step(id="s1", tool="flaky", intent="i", success_criterion="it answers")])
    replayed = StepResult(step_id="s1", tool="flaky", status="cached", result={"ok": True, "posted": 1})

    verdict = checks.verify({"run_id": "r3", "task": "demo"}, plan, [replayed], ledger)

    gate = next(p for p in verdict.predicates if p.name == "each_success_has_evidence")
    assert (gate.expected, gate.actual, gate.passed) == (1, 1, True)
    assert verdict.status == "pass"
    ledger.close()


def test_audit_trail_fails_open_when_a_step_has_no_terminal_event(tmp_runs: Path) -> None:
    """s2 claims success with nothing on record; unrelated retry noise must not vouch for it.

    The frozen `loop.verify` passes this run: it only checks that the *count* of terminal events
    reaches len(executed), and s0's three `step.failed` events are more than enough.
    """
    ledger = _ledger_with_started("r6", tmp_runs)
    ledger.append_event(Event.new("r6", "step.succeeded", step_id="s1", tool="flaky"))
    for _ in range(3):
        ledger.append_event(Event.new("r6", "step.failed", step_id="s0", tool="flaky"))  # noise
    plan = Plan(goal="demo", steps=[Step(id=f"s{i}", tool="flaky", intent="i", success_criterion="ok")
                                    for i in (1, 2)])
    claims = [StepResult(step_id="s1", tool="flaky", status="succeeded", result={"ok": True}),
              StepResult(step_id="s2", tool="flaky", status="succeeded", result={"ok": True})]

    verdict = checks.verify({"run_id": "r6", "task": "demo"}, plan, claims, ledger)

    gate = next(p for p in verdict.predicates if p.name == "audit_trail_complete")
    assert gate.passed is False and "no terminal event" in (gate.detail or "")
    assert verdict.status == "fail", "s2 has no terminal event on record"
    ledger.close()


def test_empty_task_is_blocked_not_green(tmp_runs: Path) -> None:
    ledger = _ledger_with_started("r4", tmp_runs)
    verdict = checks.verify({"run_id": "r4", "task": ""}, Plan(goal=""), [], ledger)

    assert verdict.status == "blocked" and verdict.summary == "No task given"
    assert "non_empty_goal" in {p.name for p in verdict.failed}
    assert run_task("", run_root=tmp_runs, offline=True, tools="demo")["verdict"]["status"] == "blocked"
    ledger.close()


def test_silent_skip_fails_the_gate(tmp_runs: Path) -> None:
    ledger = _ledger_with_started("r5", tmp_runs)
    plan = Plan(goal="demo", steps=[Step(id="s1", tool="flaky", intent="i", success_criterion="it answers")])
    skipped = StepResult(step_id="s1", tool="flaky", status="skipped", error=None)  # no reason recorded

    verdict = checks.verify({"run_id": "r5", "task": "demo"}, plan, [skipped], ledger)

    assert "no_silent_skips" in {p.name for p in verdict.failed}
    assert verdict.status == "blocked", "a skip with no hard failure waits on a human"
    ledger.close()


# ------------------------------------------------------------------ replan
def test_replan_happens_once_and_never_for_a_fatal_failure() -> None:
    manifests = {"flaky": flaky_manifest()}
    flaky = StepResult(step_id="s1", tool="flaky", status="failed", error=TIMEOUT_ERR)
    fatal = StepResult(step_id="s1", tool="erp", status="failed", error=REJECTED_422["error"],
                       result=dict(REJECTED_422))
    done = {"s0": StepResult(step_id="s0", tool="flaky", status="succeeded", result={"ok": True})}

    once = replan.replan("post the invoice", flaky, done, manifests, offline=True)
    assert once.planned and once.source == "heuristic" and not once.skipped

    spent = replan.replan("post the invoice", flaky, done, manifests, offline=True, used=replan.MAX_REPLANS)
    assert spent.skipped and not spent.planned and spent.plan.steps == []

    refused = replan.replan("post the invoice", fatal, done, manifests, offline=True)
    assert refused.skipped and refused.detail == "fatal", "no route reaches a payload the server refused"
    assert refused.plan.steps == [] and not refused.planned


# ------------------------------------------------------------------ B1 findings carried forward
def test_f3_rerecording_the_same_attempt_is_data_not_a_crash(tmp_runs: Path) -> None:
    ledger = Ledger(tmp_runs / "_ledger.sqlite3", run_root=tmp_runs)
    ex = Executor(ledger, "r1", {"flaky": flaky_manifest()}, {"flaky": lambda: {"ok": True}})
    assert ex.run_step(flaky_step(), 1).status == "succeeded"
    try:
        again = ex.run_step(flaky_step(), 1)  # same (run, step, attempt)
    except sqlite3.IntegrityError as exc:  # the F3 defect
        pytest.fail(f"re-recording an attempt escaped as a crash: {exc}")
    assert again is not None
    ledger.close()


def test_run_id_reuse_does_not_resume_in_place(tmp_runs: Path) -> None:
    """Why resume forks a run_id: runs.start_run is an INSERT into an append-only ledger."""
    out = run_task("demo", run_root=tmp_runs, offline=True, tools="demo")
    with pytest.raises(sqlite3.IntegrityError):
        run_task("demo", run_root=tmp_runs, offline=True, run_id=out["run_id"], tools="demo")