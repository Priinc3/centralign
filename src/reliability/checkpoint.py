"""Checkpoint + resume. The ledger is the durable state; a checkpoint only records how far
this process got, so a resume can say out loud what it inherited.

Resume means re-entering the loop, not reimplementing it: `run_task` is a function of
(task, manifests, ledger), and every (tool, args) pair that already succeeded replays from
the idempotency index instead of executing again. So `--resume` re-runs the same task under a
*new* run_id — `runs.start_run` is an INSERT and the ledger is append-only, so a run_id is
never recycled — and records `resumed_from` in the new run's checkpoint and audit trail.

What a checkpoint adds over `state.json`: the reliability counters the loop does not track
(attempts spent, replans used, why a retry stopped) and the identity of the run it continues.

  python -m src.reliability.checkpoint --runs runs --resume <run_id>
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from ..contracts.events import ACTOR_SYSTEM, Event, redact, utc_now
from ..ledger.store import Ledger, new_run_id

CKPT_NAME = "checkpoint.json"
LEDGER_NAME = "_ledger.sqlite3"


def save(run_dir: str | os.PathLike[str], checkpoint: dict[str, Any]) -> Path:
    """Atomic write of the run's reliability checkpoint (tmp + replace, so a crash leaves
    the previous one intact). Redacted: a checkpoint can quote tool args."""
    path = Path(run_dir) / CKPT_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    body = {**redact(checkpoint), "checkpoint_at": utc_now()}
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(body, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    os.replace(tmp, path)
    return path


def load(run_dir: str | os.PathLike[str]) -> dict[str, Any]:
    """The checkpoint, or `{}` when the run never wrote one."""
    path = Path(run_dir) / CKPT_NAME
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        return {}  # a truncated checkpoint must not block the resume; the ledger is the truth


def inherited(ledger: Ledger, run_id: str) -> dict[str, dict[str, Any]]:
    """step_id -> the last attempt row of `run_id`. What a resume gets for free."""
    latest: dict[str, dict[str, Any]] = {}
    for row in ledger.steps_for_run(run_id):
        latest[row["step_id"]] = row
    return latest


def resume(
    run_root: str | os.PathLike[str],
    run_id: str,
    /,
    *,
    offline: bool | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Continue the work of `run_id`: re-run its task under a new run_id, replaying what is done.

    Raises KeyError when the run is unknown — resuming nothing is a mistake worth hearing about.
    `offline` defaults to the original run's setting. Any `run_task` kwarg is forwarded, so the
    same kwargs dict that started the run can be handed straight to `resume`.
    """
    run_root = Path(run_root)
    kwargs.pop("run_root", None)  # positional-only above, so this lands here rather than clashing
    ledger = Ledger(run_root / LEDGER_NAME, run_root=run_root)
    try:
        row = ledger.get_run(run_id)
        if row is None:
            raise KeyError(f"unknown run_id {run_id!r} in {run_root / LEDGER_NAME}")
        done = inherited(ledger, run_id)
        new_id = new_run_id()
        # First thing that happens to the new run, so the audit trail reads in order.
        ledger.append_event(
            Event.new(new_id, "run.stage", actor=ACTOR_SYSTEM,
                      payload={"stage": "resume", "resumed_from": run_id, "task": row["task"],
                               "inherited_steps": sorted(done)})
        )
        from ..runtime.loop import run_task  # noqa: PLC0415 - avoids an import cycle at module load

        out = run_task(
            row["task"],
            run_id=new_id,
            run_root=run_root,
            offline=bool(row["offline"]) if offline is None else offline,
            ledger=ledger,
            **kwargs,
        )
        save(
            run_root / new_id,
            {
                "stage": out["status"],
                "resumed_from": run_id,
                "task": row["task"],
                "plan_source": out["plan_source"],
                "inherited_steps": {sid: r["status"] for sid, r in done.items()},
                "steps": out["steps"],
            },
        )
        return {**out, "resumed_from": run_id, "inherited": {sid: r["status"] for sid, r in done.items()}}
    finally:
        ledger.close()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m src.reliability.checkpoint", description=__doc__)
    ap.add_argument("--runs", default="runs", help="run root dir (default: runs/)")
    ap.add_argument("--resume", metavar="RUN_ID", default=None, help="run to continue")
    ap.add_argument("--json", action="store_true", help="print the result as JSON")
    args = ap.parse_args(argv)
    if not args.resume:
        ap.error("--resume <run_id> is required")

    out = resume(args.runs, args.resume)
    if args.json:
        print(json.dumps(out, indent=2, default=str))
    else:
        print(f"resumed {args.resume} -> run {out['run_id']} [{out['status']}] verdict={out['verdict']['status']}")
        print(f"inherited: {out['inherited']}")
        print(f"steps:     {out['steps']}")
        print(f"evidence:  {out['evidence']}")
    return 0 if out["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())