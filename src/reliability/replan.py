"""One replan after a failed step, reusing whatever already succeeded.

Why exactly one: a plan that fails the same way twice is not converging, and a planner that
gets unlimited re-rolls turns a broken ERP into an unbounded spend. The planner is asked
once more with the failure text in the prompt; a fatal failure is never replanned at all,
because no route reaches a payload the server already refused.

"Keeps the succeeded cache" is free rather than reimplemented: a step that already ran
recorded its (tool, args) idempotency key, so the replanned copy of that step replays from
the ledger instead of executing. `Replan.reused` names which ones, so the evidence says so.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from ..runtime.planner import Plan, Step, describe, make_plan
from .retry import is_retryable

MAX_REPLANS = 1  # ponytail: one re-roll per run. More needs a convergence signal we do not have.


@dataclass(frozen=True)
class Replan:
    """Outcome of the replan attempt. `skipped` means "no replan was warranted"."""

    plan: Plan
    source: str
    reason: str
    reused: tuple[str, ...] = ()
    skipped: bool = False
    detail: str = ""

    @property
    def planned(self) -> bool:
        return not self.skipped and bool(self.plan.steps)


def replan(
    task: str,
    failure: Any,
    results: Mapping[str, Any],
    manifests: Mapping[str, Any],
    *,
    offline: bool = True,
    client: Any | None = None,
    used: int = 0,
    failed_step: Step | None = None,
) -> Replan:
    """Ask the planner for a different route to `task`, once, after `failure` failed.

    `results` is the step_id -> StepResult map from the attempt that just failed; whatever
    resolved there is carried into the new plan so its ledger row replays instead of re-running.
    Returns a skipped Replan (never raises) when the failure is fatal or the budget is spent —
    a caller can always use `Replan.plan`, which is the original goal with no steps.
    """
    empty = Plan(goal=task)
    if used >= MAX_REPLANS:
        return Replan(empty, "none", "replan budget spent", skipped=True,
                      detail=f"{used}/{MAX_REPLANS} replans already used")
    if not is_retryable(failure):
        return Replan(empty, "none", f"fatal failure, retrying cannot help: {failure.error}",
                      skipped=True, detail="fatal")

    where = f" step {failed_step.id} ({failed_step.tool})" if failed_step else ""
    brief = f"{task} | the previous attempt failed{where}: {failure.error} | choose a different route"
    plan, source = make_plan(brief, manifests, offline=offline, client=client)
    kept = {s.id for s in plan.steps}
    reused = tuple(sorted(sid for sid, r in results.items() if getattr(r, "resolved", False) and sid in kept))
    return Replan(
        plan=plan,
        source=source,
        reason=f"replanned after {failure.step_id} failed: {failure.error}",
        reused=reused,
    )


def summary(replan_result: Replan) -> str:
    """One line for the state file and the run.stage event."""
    if replan_result.skipped:
        return f"no replan: {replan_result.detail}"
    return f"replan={describe(replan_result.plan)} source={replan_result.source} reused={list(replan_result.reused)}"


if __name__ == "__main__":  # pragma: no cover - inspect the replan for a task, no execution
    from ..tools.manifest_registry import registry  # noqa: PLC0415 - sibling registry, planning only

    plan, source = make_plan("find latest invoice from Company X and post it to the ERP", registry(), offline=True)
    print(f"{source}: {describe(plan)}")