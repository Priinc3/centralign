"""Operator loop: Goal→Understand→Plan→Execute→Observe→Adapt→Verify→Complete.

Deterministic by construction: the LLM only plans, the executor only dispatches
through manifests, and Verify grades observable predicates — so the same task +
manifests + ledger produce the same evidence bundle.

Run offline with no API key:  python -m src.runtime.loop --task "demo" --offline
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Callable, Mapping

from ..contracts.events import ACTOR_SYSTEM, Event, utc_now
from ..contracts.tools import ToolManifest
from ..contracts.verdict import Verdict
from ..ledger.evidence import write_evidence, write_state
from ..ledger.store import Ledger, new_run_id
from ..reliability.replan import replan
from ..reliability.retry import RetryPolicy, run_step_with_retry
from .executor import Executor, StepResult
from .planner import Plan, Step, describe, make_plan

RUN_ROOT = Path(os.environ.get("CENTRALIGN_RUNS", "runs"))
LEDGER_NAME = "_ledger.sqlite3"
MAX_ATTEMPTS = 1  # the outer sweep no longer retries; the policy does (Phase 04)
POLICY = RetryPolicy()  # max_attempts=3, exponential backoff, seeded jitter


# --------------------------------------------------------------------- registry
def demo_manifests() -> dict[str, ToolManifest]:
    """Fallback registry so the offline demo works before Phase 02's tools land."""
    return {
        "echo_note": ToolManifest(
            name="echo_note",
            description="Append a line to the operator run log (offline demo stand-in for notify/tell-me).",
            parameters={
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
                "additionalProperties": False,
            },
            risk="write",
            requires_approval=False,
        )
    }


def demo_callables() -> dict[str, Callable[..., Any]]:
    def echo_note(text: str) -> dict[str, Any]:
        return {"noted": text}

    return {"echo_note": echo_note}


def load_registry() -> tuple[dict[str, ToolManifest], dict[str, Callable[..., Any]], str]:
    """Use Phase 02's registry when usable; otherwise the built-in demo tools.

    Contract I announce in prompts/parallel-G1/COMM.md: expose load() -> {name: ToolManifest}
    and callables() -> {name: fn}. Their in-progress manifests()/execute() shape is also accepted,
    so integration works without either side waiting.
    """
    try:
        from src.tools import manifest_registry as reg  # noqa: PLC0415 - optional sibling module
    except ImportError as exc:
        print(f"[warn] no Phase 02 registry yet ({exc}); using built-in demo tools", file=sys.stderr)
        return demo_manifests(), demo_callables(), "builtin-demo"
    try:
        loader = getattr(reg, "load", None) or getattr(reg, "registry", None)
        if loader is not None and hasattr(reg, "callables"):
            manifests = {}
            for key, m in loader().items():
                manifest = m if isinstance(m, ToolManifest) else ToolManifest.model_validate(m)
                manifests[manifest.name or key] = manifest
            return manifests, dict(reg.callables()), f"src.tools.manifest_registry:{loader.__name__}()"
        if hasattr(reg, "manifests") and hasattr(reg, "execute"):
            manifests, rejected = coerce_manifests(reg.manifests())
            if not manifests:
                raise ValueError(f"no manifest matched the frozen contract: {rejected}")

            def wrap(name: str) -> Callable[..., Any]:
                def run(**args: Any) -> Any:
                    result = reg.execute(name, args)
                    if isinstance(result, dict) and result.get("ok") is False:
                        raise RuntimeError(result.get("error") or f"{name} failed")
                    return result

                return run

            return manifests, {n: wrap(n) for n in manifests}, "src.tools.manifest_registry:manifests+execute"
        raise ValueError("registry exposes neither load()+callables() nor manifests()+execute()")
    except Exception as exc:  # noqa: BLE001 - a broken registry must not stop the loop
        print(f"[warn] Phase 02 registry unusable ({exc}); using built-in demo tools", file=sys.stderr)
        return demo_manifests(), demo_callables(), "builtin-demo(broken-registry)"


def coerce_manifests(raws: list[Any]) -> tuple[dict[str, ToolManifest], list[str]]:
    """Manifest dicts -> ToolManifest, tolerating `input_schema` as an alias of `parameters`."""
    out: dict[str, ToolManifest] = {}
    rejected: list[str] = []
    for raw in raws:
        try:
            data = dict(raw.model_dump() if isinstance(raw, ToolManifest) else raw)
            data.setdefault("parameters", data.pop("input_schema", None) or
                            {"type": "object", "properties": {}, "required": [], "additionalProperties": False})
            manifest = ToolManifest.model_validate(data)
            out[manifest.name] = manifest
        except Exception as exc:  # noqa: BLE001
            name = getattr(raw, "name", None) or (raw.get("name") if isinstance(raw, dict) else raw)
            reason = next((ln.strip() for ln in str(exc).splitlines() if ln.strip().startswith("Value error")), str(exc))
            rejected.append(f"{name}: {reason[:100]}")
    return out, rejected


# --------------------------------------------------------------------- stages
def goal_state(run_id: str, task: str) -> dict[str, Any]:
    return {"run_id": run_id, "task": task, "goal": task, "stage": "goal", "at": utc_now()}


def understand(task: str, manifests: Mapping[str, ToolManifest]) -> dict[str, Any]:
    """No LLM: extract what the task needs, not what it says."""
    text = task.lower()
    needs = {
        "find_data": any(w in text for w in ("find", "latest", "search", "get", "fetch", "read")),
        "write_system": any(w in text for w in ("enter", "post", "record", "create", "save", "add")),
        "notify_human": any(w in text for w in ("tell", "notify", "report", "inform", "message")),
        "money": any(ch.isdigit() for ch in task) and any(w in text for w in ("amount", "total", "due", "$")),
    }
    return {
        "stage": "understand",
        "needs": needs,
        "available_tools": sorted(manifests),
        "constraints": ["dispatch only via manifest", "verify with observable predicates", "never log secrets"],
    }


def verify(state: dict[str, Any], plan: Plan, results: list[StepResult], ledger: Ledger) -> Verdict:
    """Independent predicates over ledger + step rows — not the executor's own opinion.

    The predicates live in Phase 04 (`src/verifier/checks.py`): it fixes the fail-OPEN
    `audit_trail_complete` and the cached-vs-succeeded miscount in the copy that used to be
    frozen here. Same signature, same predicate names, same `blocked` semantics.
    """
    from ..verifier.checks import verify as _verify  # noqa: PLC0415 - circular otherwise

    return _verify(state, plan, results, ledger)


def adapt(state: dict[str, Any], results: list[StepResult], attempt: int) -> list[str]:
    """What the outer sweep repeats. `MAX_ATTEMPTS = 1` means: nothing — retries are the
    policy's job now (`run_step_with_retry`), which also triages fatal vs transient."""
    if attempt >= MAX_ATTEMPTS:
        return []
    retry: list[str] = []
    for r in results:
        if r.status == "failed":
            retry.append(r.step_id)
    return retry


# --------------------------------------------------------------------- loop
def run_task(
    task: str,
    *,
    run_id: str | None = None,
    run_root: Path | str = RUN_ROOT,
    offline: bool = False,
    manifests: Mapping[str, ToolManifest] | None = None,
    callables: Mapping[str, Callable[..., Any]] | None = None,
    ledger: Ledger | None = None,
    client: Any | None = None,
    tools: str = "auto",
    authorizer: Callable[[ToolManifest, dict[str, Any]], str] | None = None,
) -> dict[str, Any]:
    """Run one task end to end. `tools`: auto = Phase 02 registry if usable, else built-in demo;
    demo = force the built-in registry so the offline demo never depends on sibling state.
    `authorizer` is the HITL/policy gate: `allow|approve|deny` per (manifest, args), so Phase 05's
    CLI can pass `src.reliability.hitl.authorizer`; without one every tool is allowed."""
    run_id = run_id or new_run_id()
    run_root = Path(run_root)
    run_dir = run_root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    if manifests is None or callables is None:
        auto_m, auto_c, source = (demo_manifests(), demo_callables(), "builtin-demo") if tools == "demo" \
            else load_registry()
        manifests = manifests if manifests is not None else auto_m
        callables = callables if callables is not None else auto_c
    else:
        source = "injected"
    own_ledger = ledger is None
    ledger = ledger or Ledger(run_root / LEDGER_NAME, run_root=run_root)

    state: dict[str, Any] = goal_state(run_id, task)
    ledger.start_run(run_id, task, goal=task, offline=offline)
    ledger.append_event(
        Event.new(run_id, "run.started", actor=ACTOR_SYSTEM,
                  payload={"task": task, "offline": offline, "tools": sorted(manifests), "registry": source})
    )
    write_state(run_dir, state)

    # understand
    state.update(understand(task, manifests))
    ledger.set_stage(run_id, "understand")
    write_state(run_dir, state)

    # plan
    plan, plan_source = make_plan(task, manifests, offline=offline, client=client)
    state["plan"] = plan.to_contract()
    state["plan_source"] = plan_source
    state["dag"] = describe(plan)
    ledger.set_stage(run_id, "plan")
    ledger.append_event(
        Event.new(run_id, "step.planned", actor=ACTOR_SYSTEM,
                  payload={"goal": plan.goal, "source": plan_source, "dag": state["dag"]})
    )
    write_state(run_dir, state)

    # execute → observe → adapt
    executor = Executor(ledger, run_id, manifests, callables, authorizer=authorizer)
    steps = plan.topo_order()
    results: dict[str, StepResult] = {}
    attempt = 1

    def execute(step: Step, seq: int) -> None:
        blocked_by = [d for d in step.depends_on if d in results and not results[d].resolved]
        if blocked_by:
            results[step.id] = StepResult(
                step_id=step.id, tool=step.tool, status="skipped",
                error=f"upstream step(s) {blocked_by} did not succeed",
            )
            executor.emit("step.failed", step_id=step.id, tool=step.tool, error=results[step.id].error)
            return
        results[step.id] = run_step_with_retry(executor, step, seq, attempt=attempt, policy=POLICY,
                                               upstream={d: results[d] for d in step.depends_on})
        state["results"] = {k: v.status for k, v in results.items()}
        write_state(run_dir, state)

    def sweep() -> None:
        ledger.set_stage(run_id, "execute")
        ledger.append_event(Event.new(run_id, "run.stage", actor=ACTOR_SYSTEM,
                                      payload={"stage": "execute", "attempt": attempt}))
        for seq, step in enumerate(steps, start=1):
            execute(step, seq)

    sweep()

    ledger.set_stage(run_id, "observe")
    failed = [r.step_id for r in results.values() if r.status == "failed"]
    state["observed"] = {
        "ok": [r.step_id for r in results.values() if r.ok],
        "failed": failed,
        "skipped": [r.step_id for r in results.values() if r.status == "skipped"],
    }
    ledger.append_event(Event.new(run_id, "run.stage", actor=ACTOR_SYSTEM,
                                  payload={"stage": "observe", **state["observed"]}))
    write_state(run_dir, state)

    retry = failed if adapt(state, list(results.values()), attempt) else []
    state["adapt"] = {"attempt": attempt, "retrying": retry}
    write_state(run_dir, state)
    if retry:
        ledger.set_stage(run_id, "adapt")
        ledger.append_event(Event.new(run_id, "run.stage", actor=ACTOR_SYSTEM,
                                      payload={"stage": "adapt", "attempt": attempt, "retrying": retry}))
        attempt += 1
        for seq, step in enumerate(steps, start=1):
            if step.id in retry:
                execute(step, seq)
        ledger.set_stage(run_id, "observe")

    # replan: one re-roll through the planner with the failure in the brief, reusing what
    # already succeeded from the ledger. `failed` predates any re-execution above, so re-derive.
    failure = next((r for r in results.values() if r.status == "failed"), None)
    if failure is not None:  # replan() reads failure.error, so a clean sweep never calls it
        again = replan(task, failure, results, manifests, offline=offline, client=client)
        ledger.append_event(Event.new(run_id, "run.stage", actor=ACTOR_SYSTEM,
                                      payload={"stage": "replan", "planned": again.planned,
                                               "reused": list(again.reused), "detail": again.detail}))
        if again.planned:
            plan, plan_source = again.plan, f"replan:{again.source}"
            steps = plan.topo_order()
            ledger.set_stage(run_id, "execute")
            for seq, step in enumerate(steps, start=1):
                execute(step, seq)
            ledger.set_stage(run_id, "observe")

    ordered = [results[s.id] for s in steps if s.id in results]
    state["stage"] = "observe"

    # verify
    verdict = verify(state, plan, ordered, ledger)
    state["verdict"] = verdict.to_contract()
    ledger.set_stage(run_id, "verify")

    # complete
    status = "completed" if verdict.status == "pass" else ("blocked" if verdict.status == "blocked" else "failed")
    ledger.finish_run(run_id, status, verdict=verdict.to_contract(), evidence_dir=str(run_dir))
    ledger.append_event(
        Event.new(run_id, "run.completed" if status == "completed" else "run.failed",
                  actor=ACTOR_SYSTEM, payload={"status": status, "verdict": verdict.status})
    )
    state["stage"] = "complete"
    state["status"] = status
    state["completed_at"] = utc_now()
    write_state(run_dir, state)

    evidence = write_evidence(
        run_dir,
        run={**(ledger.get_run(run_id) or {}), "run_id": run_id, "task": task, "plan_source": plan_source},
        plan=plan.to_contract(),
        steps=[_step_row(plan, s, results[s.id]) for s in steps if s.id in results],
        events=ledger.events_for_run(run_id),
        verdict=verdict,
        manifests=[m.to_contract() for m in manifests.values()],
        limits=[
            f"planner={plan_source}",
            "LLM plans only; executor dispatches by manifest name only",
            "one operator: read-only tools run unattended, side-effecting tools need a "
            "human approval on the queue",
        ],
    )
    if own_ledger:
        ledger.close()
    return {
        "run_id": run_id,
        "status": status,
        "verdict": verdict.to_contract(),
        "run_dir": str(run_dir),
        "evidence": str(evidence),
        "state": str(run_dir / "state.json"),
        "steps": [r.status for r in ordered],
        "dag": state["dag"],
        "plan_source": plan_source,
        "registry": source,
    }


def _step_row(plan: Plan, step: Step, result: StepResult) -> dict[str, Any]:
    return {
        "step_id": step.id,
        "seq": plan.steps.index(step),
        "tool": step.tool,
        "args": step.args,
        "depends_on": step.depends_on,
        "intent": step.intent,
        "success_criterion": step.success_criterion,
        "status": result.status,
        "result": result.result,
        "error": result.error,
        "attempt": result.attempt,
        "idem_key": result.idem_key,
        "replayed_from_run": result.from_run,
    }


# --------------------------------------------------------------------- cli
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m src.runtime.loop", description="Run one operator task.")
    ap.add_argument("--task", required=True)
    ap.add_argument("--offline", action="store_true", help="skip the LLM; use the deterministic heuristic planner")
    ap.add_argument("--run-id", default=None)
    ap.add_argument("--runs", default=str(RUN_ROOT), help="run root dir (default: runs/)")
    ap.add_argument("--tools", choices=("auto", "demo"), default="auto",
                    help="auto: use the Phase 02 registry when usable; demo: built-in tool, no sibling dependency")
    ap.add_argument("--json", action="store_true", help="print the result summary as JSON")
    args = ap.parse_args(argv)

    out = run_task(args.task, run_id=args.run_id, run_root=Path(args.runs), offline=args.offline,
                   tools=args.tools)
    if args.json:
        print(json.dumps(out, indent=2, default=str))
    else:
        print(f"run {out['run_id']} [{out['status']}] verdict={out['verdict']['status']} plan={out['plan_source']}")
        print(f"dag: {out['dag']}")
        print(f"steps: {out['steps']}")
        print(f"evidence: {out['evidence']}")
        print(f"state:    {out['state']}")
    return 0 if out["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
