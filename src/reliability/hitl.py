"""HITL: a human signs off on anything the policy only `approve`s.

Phase 03's gate writes one append-only file that is both its decision audit trail and the
approval queue (`company.yaml approval.queue`, `data/gate.jsonl`). This module reads that
queue and closes a request by *appending* a decision record — the file is never rewritten in
place, so the audit trail and the queue cannot drift apart.

Deny by default: only a request whose latest record still says `queue: "pending"` can be
closed, an unknown id is an error rather than a silent no-op, and every decision is recorded
with who made it.

  python -m src.reliability.hitl --pending
  python -m src.reliability.hitl --approve <request_id> --approver alice
  python -m src.reliability.hitl --deny    <request_id> --approver alice --reason "wrong vendor"
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any

from ..contracts.events import redact
from ..contracts.tools import ToolManifest

GRANTED = "granted"
DENIED = "denied"
PENDING = "pending"
CLOSED = "closed"


class ApprovalError(ValueError):
    """The request cannot be decided: unknown, already closed, or no approver named."""


def queue_path() -> Path:
    """The queue named by context/company.yaml, so the gate and this CLI cannot disagree."""
    from ..policy.loader import ROOT, load_context  # noqa: PLC0415 - keeps import cheap for the CLI

    return ROOT / str(load_context()["company"]["approval"]["queue"])


def amount_threshold() -> float:
    """Phase 03's auto-post ceiling. Read from the policy files, never re-declared here."""
    from ..policy.loader import load_context  # noqa: PLC0415

    return float(load_context()["policies"]["max_amount_auto_post"])


def read(path: str | os.PathLike[str] | None = None) -> list[dict[str, Any]]:
    """Every record in the queue file, oldest first. Unparseable lines are skipped, not fatal."""
    p = Path(path) if path else queue_path()
    if not p.is_file():
        return []
    out: list[dict[str, Any]] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


def latest(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """request_id -> its most recent record. Last write wins; that is what closed means."""
    out: dict[str, dict[str, Any]] = {}
    for rec in records:
        rid = rec.get("request_id")
        if rid:
            out[rid] = rec
    return out


def pending(path: str | os.PathLike[str] | None = None) -> list[dict[str, Any]]:
    """Requests still awaiting a human, oldest first. Records without a request_id (allow/deny)
    are already decided and never appear here."""
    return [rec for rec in latest(read(path)).values() if rec.get("queue") == PENDING]


def decided(request_id: str, path: str | os.PathLike[str] | None = None) -> bool:
    """True when a human has already released this request."""
    rec = latest(read(path)).get(request_id)
    return bool(rec) and rec.get("queue") == CLOSED and rec.get("verdict") == GRANTED


def log_decision(record: dict[str, Any], path: str | os.PathLike[str] | None = None) -> Path:
    """Append one redacted record in Phase 03's `gate.jsonl` shape. The audit trail is the queue."""
    p = Path(path) if path else queue_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "tool": record.get("tool"),
        "verdict": record.get("verdict"),
        "reason": record.get("reason"),
        "risk": record.get("risk", "n/a"),
        "amount": record.get("amount"),
        "domain": record.get("domain"),
        "request_id": record.get("request_id"),
        "queue": record.get("queue", PENDING),
    }
    if record.get("approver"):
        row["approver"] = record["approver"]
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(redact(row)) + "\n")
    return p


def decide(
    request_id: str,
    *,
    approver: str,
    approve: bool = True,
    reason: str = "",
    path: str | os.PathLike[str] | None = None,
) -> dict[str, Any]:
    """Close `request_id` as granted or denied. Raises ApprovalError if it is not pending."""
    if not approver.strip():
        raise ApprovalError("an approver id is required; an unowned decision is not a decision")
    rec = latest(read(path)).get(request_id)
    if rec is None:
        raise ApprovalError(f"unknown request_id {request_id!r}")
    if rec.get("queue") != PENDING:
        raise ApprovalError(f"request {request_id} is already {rec.get('queue')!r}")
    closed = {
        **rec,
        "verdict": GRANTED if approve else DENIED,
        "queue": CLOSED,
        "approver": approver,
        "reason": reason or rec.get("reason") or "",
        "decided_on": request_id,
    }
    log_decision(closed, path)
    return closed


def ensure_request(
    tool: str,
    *,
    amount: float | None = None,
    domain: str | None = None,
    risk: str = "write",
    reason: str = "",
    path: str | os.PathLike[str] | None = None,
) -> dict[str, Any]:
    """The latest request for this exact call, or a new one.

    Keyed on (tool, amount, domain) and *not* re-queued while one exists, so a retried or
    resumed run asks the human once and a granted request keeps releasing the call — a fresh
    id per attempt would strand every grant.
    """
    key = (tool, amount, domain)
    prior = [r for r in read(path) if (r.get("tool"), r.get("amount"), r.get("domain")) == key]
    if prior:
        return prior[-1]  # newest record for this call: still pending, or already decided
    rid = uuid.uuid4().hex[:12]
    rec = {
        "tool": tool, "verdict": "approve", "reason": reason, "risk": risk,
        "amount": amount, "domain": domain, "request_id": rid, "queue": PENDING,
    }
    log_decision(rec, path)
    return rec


def _amount(args: dict[str, Any]) -> float | None:
    for key in ("amount", "total", "value"):
        raw = args.get(key)
        if isinstance(raw, bool):
            continue
        if isinstance(raw, (int, float)):
            return float(raw)
        if isinstance(raw, str):
            try:
                return float(raw.replace(",", "").strip())
            except ValueError:
                continue
    return None


def authorizer(
    manifest: ToolManifest,
    args: dict[str, Any],
    *,
    path: str | os.PathLike[str] | None = None,
    threshold: float | None = None,
    log: bool = True,
) -> str:
    """`allow` | `approve` | `deny`, for `Executor(authorizer=...)`.

    Approval is required when the manifest declares `requires_approval` or the call carries an
    amount over the auto-post ceiling — Phase 03's threshold, read from the policy files rather
    than re-declared. Anything not explicitly allowed stays queued for a human; nothing here
    grants itself.
    """
    amount = _amount(args)
    limit = amount_threshold() if threshold is None else threshold
    if not manifest.requires_approval and not (amount is not None and amount > limit):
        return "allow"
    why = f"{manifest.name} requires approval" if manifest.requires_approval \
        else f"amount {amount} over auto-post {limit}"
    if not log:
        return "approve"
    rec = ensure_request(manifest.name, amount=amount, risk=manifest.risk, reason=why, path=path)
    return "allow" if decided(rec["request_id"], path) else "approve"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m src.reliability.hitl", description=__doc__)
    ap.add_argument("--pending", action="store_true", help="list requests awaiting a human")
    ap.add_argument("--approve", metavar="REQUEST_ID", default=None)
    ap.add_argument("--deny", metavar="REQUEST_ID", default=None)
    ap.add_argument("--approver", default="", help="who is signing off (recorded in the audit trail)")
    ap.add_argument("--reason", default="", help="why")
    ap.add_argument("--queue", default=None, help="queue file (default: company.yaml approval.queue)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    where = args.queue
    if args.approve or args.deny:
        rid = args.approve or args.deny
        try:
            out = decide(rid, approver=args.approver, approve=bool(args.approve),
                         reason=args.reason, path=where)
        except ApprovalError as exc:
            print(f"refused: {exc}", file=sys.stderr)
            return 2
        print(json.dumps(out, indent=2) if args.json else f"{rid} {out['verdict']} by {out['approver']}")
        return 0
    if args.pending:
        items = pending(where)
        if args.json:
            print(json.dumps(items, indent=2))
        elif not items:
            print("no pending approvals")
        else:
            for rec in items:
                print(f"{rec['request_id']}  {rec['tool']}  amount={rec['amount']}  {rec['reason']}")
        return 0
    ap.error("one of --pending / --approve / --deny is required")


if __name__ == "__main__":
    raise SystemExit(main())