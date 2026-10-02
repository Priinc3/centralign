"""Evidence bundle writer: one JSON file per run that proves what happened.

Layout: runs/<run_id>/{state.json,evidence.json,events.jsonl,tools.json}
Writes are atomic (tmp + os.replace) so a crashed run never leaves half a bundle.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from ..contracts.events import redact, utc_now
from ..contracts.verdict import Verdict

BUNDLE_VERSION = 1


def _write_json(path: Path, data: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    os.replace(tmp, path)
    return path


def write_state(run_dir: Path, state: dict[str, Any]) -> Path:
    """Checkpoint after every stage (Phase 04 resumes from the last one)."""
    return _write_json(run_dir / "state.json", {**redact(state), "checkpoint_at": utc_now()})


def write_evidence(
    run_dir: str | os.PathLike[str],
    *,
    run: dict[str, Any],
    plan: dict[str, Any] | None,
    steps: list[dict[str, Any]],
    events: list[dict[str, Any]],
    verdict: Verdict,
    manifests: list[dict[str, Any]] | None = None,
    limits: list[str] | None = None,
) -> Path:
    """Write runs/<run_id>/evidence.json: steps + verdict + audit trail + tool contracts."""
    run_dir = Path(run_dir)
    executed = [s for s in steps if s["status"] == "succeeded"]  # called in THIS run
    replayed = [s for s in steps if s["status"] == "cached"]  # served from the ledger, not called
    failed = [s for s in steps if s["status"] == "failed"]
    skipped = [s for s in steps if s["status"] == "skipped"]
    bundle = {
        "bundle_version": BUNDLE_VERSION,
        "run": {
            "run_id": run.get("run_id"),
            "task": run.get("task"),
            "goal": run.get("goal"),
            "status": run.get("status"),
            "offline": bool(run.get("offline")),
            "created_at": run.get("created_at"),
            "updated_at": run.get("updated_at"),
            "plan_source": run.get("plan_source"),
        },
        "plan": plan,
        "steps": steps,
        "totals": {
            "steps": len(steps),
            "succeeded": len(executed),
            "cached": len(replayed),
            "failed": len(failed),
            "skipped": len(skipped),
            "events": len(events),
            "tools_actually_executed": sorted({s["tool"] for s in executed}),  # no silent mock autonomy
            "tools_replayed": sorted({s["tool"] for s in replayed}),
        },
        "verdict": verdict.to_contract(),
        "tools": manifests or [],
        "events": events,
        "limits": limits or [],
        "written_at": utc_now(),
    }
    _write_json(run_dir / "evidence.json", redact(bundle))
    (run_dir / "events.jsonl").write_text(
        "".join(json.dumps(e, sort_keys=True, default=str) + "\n" for e in redact(events)), encoding="utf-8"
    )
    if manifests:
        _write_json(run_dir / "tools.json", redact(manifests))
    return run_dir / "evidence.json"


def load_evidence(run_dir: str | os.PathLike[str]) -> dict[str, Any]:
    return json.loads((Path(run_dir) / "evidence.json").read_text(encoding="utf-8"))
