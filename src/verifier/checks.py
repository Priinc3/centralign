"""Verify: independent predicates over the ledger + step rows, never over the executor's word.

Drop-in for `src.runtime.loop.verify` (same signature), which should delegate here — see
REPORT HELP-4. Two things this fixes over the copy frozen into the loop:

- `each_success_has_evidence` compared a count of *cached* steps against a count of *succeeded*
  ones, so an all-cached run reported `expected: 0, actual: 0` and looked like it had verified
  nothing at all;
- `audit_trail_complete` counted `step.failed` events toward the per-step expectation, so a run
  that failed everything scored higher on the audit trail than one that succeeded.

Fail-closed: a row that claims `succeeded` or `cached` must carry a real, non-`{ok: false}`
payload. A missing or poisoned payload fails the gate instead of passing on a status word.
"""

from __future__ import annotations

from typing import Any, Iterable

from ..contracts.events import ACTOR_VERIFIER, Event
from ..contracts.verdict import Predicate, Verdict
from ..ledger.store import Ledger
from ..runtime.executor import StepResult, payload_failed

TERMINAL = ("step.succeeded", "step.cached")


def check(
    state: dict[str, Any],
    plan: Any,
    results: Iterable[StepResult],
    ledger: Ledger,
) -> list[Predicate]:
    """The six gates plus one weight-0 criterion per planned step."""
    rows = list(results)
    run_id = state["run_id"]
    goal = str(state.get("task") or "")
    claims = [r for r in rows if r.status in ("succeeded", "cached")]  # rows asserting an outcome
    failed = [r for r in rows if r.status == "failed"]
    skipped = [r for r in rows if r.status == "skipped"]
    unbacked = [r.step_id for r in claims if r.result is None or payload_failed(r.result)]
    terminal = {e["step_id"] for e in ledger.events_for_run(run_id) if e["type"] in TERMINAL}
    uncovered = [r.step_id for r in claims if r.step_id not in terminal]
    started = ledger.count_events(run_id, "run.started")

    predicates = [
        Predicate(
            name="non_empty_goal",
            kind="custom",
            statement="the run was given a non-empty task to accomplish",
            expected=True,
            actual=bool(goal.strip()),
            passed=bool(goal.strip()),
            detail=None if goal.strip() else "No task given",
            evidence_ref="runs.task",
        ),
        Predicate(
            name="plan_has_steps",
            kind="artifact",
            statement="the plan contains at least one dispatchable step",
            expected=1,
            actual=len(plan.steps),
            passed=bool(plan.steps),
            evidence_ref="plan.steps",
        ),
        Predicate(
            name="every_step_resolved",
            kind="ledger",
            statement="every planned step ended succeeded, cached or explicitly skipped",
            expected=0,
            actual=len(failed),
            passed=not failed,
            detail=", ".join(f"{r.step_id}:{r.error}" for r in failed + skipped if r.error) or None,
            evidence_ref="steps",
        ),
        Predicate(
            name="no_silent_skips",
            kind="tool_result",
            statement="no step was skipped silently (skips are recorded with a reason)",
            expected=0,
            actual=sum(1 for r in skipped if not r.error),
            passed=all(r.error for r in skipped),
            detail=", ".join(r.step_id for r in skipped if not r.error) or None,
            evidence_ref="steps",
        ),
        Predicate(
            name="each_success_has_evidence",
            kind="tool_result",
            statement="each successful step recorded a real, non-ok:false result in the ledger",
            expected=len(claims),
            actual=len(claims) - len(unbacked),
            passed=not unbacked,
            detail=", ".join(f"{sid}: no usable result payload" for sid in unbacked) or None,
            evidence_ref="steps",
        ),
        Predicate(
            name="audit_trail_complete",
            kind="event_log",
            statement="a run.started event plus one terminal event per resolved step is on record",
            expected=1 + len(claims),
            actual=started + len(terminal & {r.step_id for r in claims}),
            passed=started == 1 and not uncovered,
            detail=", ".join(f"{sid}: no terminal event" for sid in uncovered) or None,
            evidence_ref="events",
        ),
    ]
    for step, result in zip(plan.topo_order(), rows):
        predicates.append(
            Predicate(
                name=f"criterion:{step.id}",
                kind="custom",
                statement=step.success_criterion,
                expected="ok",
                actual=result.status,
                passed=result.resolved,
                weight=0,  # criteria are reported per step; the gates above decide the verdict
                detail=result.error,
                evidence_ref=f"steps/{step.id}",
            )
        )
    return predicates


def verify(state: dict[str, Any], plan: Any, results: Iterable[StepResult], ledger: Ledger) -> Verdict:
    """Grade the run and leave the `verify.checked` event behind.

    `blocked` = waiting on a human (no goal, or a skip with no hard failure). A failed tool is
    a fail, not a block: the operator's own work did not happen.
    """
    rows = list(results)
    predicates = check(state, plan, rows, ledger)
    ledger.append_event(
        Event.new(state["run_id"], "verify.checked", actor=ACTOR_VERIFIER,
                  payload={"passed": sum(p.passed for p in predicates), "total": len(predicates)})
    )
    goal_empty = not str(state.get("task") or "").strip()
    skipped_only = any(r.status == "skipped" for r in rows) and not any(r.status == "failed" for r in rows)
    return Verdict.from_predicates(
        state["run_id"],
        predicates,
        blocked=goal_empty or skipped_only,
        summary="No task given" if goal_empty else None,
        evidence_ref="evidence.json#/verdict",
    )