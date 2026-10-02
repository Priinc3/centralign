"""Risk-tiered approval gate: allow | approve | deny. Deterministic, no LLM.

Deny by default. Order is fixed and cheapest-check-first so a bad domain can never
be rescued by an amount. Every decision is appended to the file-based approval
queue (company.yaml approval.queue), which phase 04's HITL CLI reads.

Usage:
  python -m src.policy.gate --tool erp.post --amount 999999   -> approve
  python -m src.policy.gate --tool erp.post --amount 10       -> allow
  python -m src.policy.gate --domain evil.com                 -> deny
"""

from __future__ import annotations

import argparse
import json
import time
import uuid
from dataclasses import asdict, dataclass
from typing import Any

from src.policy.loader import ROOT, load_context

UNKNOWN_TOOL = "unknown.tool"


@dataclass(frozen=True)
class Decision:
    tool: str
    verdict: str  # allow | approve | deny
    reason: str
    risk: str
    amount: float | None = None
    domain: str | None = None
    request_id: str | None = None


def decide(
    tool: str = UNKNOWN_TOOL,
    amount: float | None = None,
    domain: str | None = None,
    context: dict[str, Any] | None = None,
    log: bool = True,
) -> Decision:
    ctx = context or load_context()
    specs = ctx["tools"]["tools"]
    allow = {d.lower() for d in ctx["policies"]["allowlist_domains"]}
    auto_post = float(ctx["policies"]["max_amount_auto_post"])
    ceiling = float(ctx["company"]["approval"]["amount_ceiling"])

    def done(verdict: str, reason: str, risk: str = "n/a", request_id: str | None = None) -> Decision:
        decision = Decision(tool, verdict, reason, risk, amount, domain, request_id)
        if log:
            _log(decision, ctx["company"]["approval"]["queue"])
        return decision

    # 1. Unknown tool -> deny. A tool nobody declared is a tool nobody policied.
    spec = specs.get(tool)
    if spec is None:
        return done("deny", f"tool {tool!r} not in context/tools.yaml registry")
    risk = spec["risk"]

    # 2. Domain not allowlisted -> deny, regardless of amount.
    if domain is not None and domain.lower() not in allow:
        return done("deny", f"domain {domain!r} not in allowlist", risk)

    # 3. Money: ceiling is a hard stop, anything over it is refused, not queued.
    if amount is not None:
        if amount < 0:
            return done("deny", f"negative amount {amount}", risk)
        if amount > ceiling:
            return done("deny", f"amount {amount} over ceiling {ceiling}", risk)
        if amount > auto_post:
            return done(
                "approve",
                f"amount {amount} over auto-post {auto_post}",
                risk,
                request_id=uuid.uuid4().hex[:12],
            )

    # 4. Amount-scoped tool called with no amount -> a human confirms it.
    if amount is None and spec.get("amount_scoped"):
        return done("approve", f"{tool} needs an amount before posting", risk, request_id=uuid.uuid4().hex[:12])

    return done("allow", f"{risk} risk within policy", risk)


def _log(decision: Decision, queue: str) -> None:
    path = ROOT / queue
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        **asdict(decision),
        "queue": "pending" if decision.verdict == "approve" else "closed",
    }
    # ponytail: one append-only file is both the decision audit trail and the approval queue.
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m src.policy.gate", description=__doc__)
    parser.add_argument("--tool", default=UNKNOWN_TOOL, help="tool id, e.g. erp.post")
    parser.add_argument("--amount", type=float, default=None)
    parser.add_argument("--domain", default=None, help="target host, checked against allowlist")
    parser.add_argument("--json", action="store_true", help="print the whole decision record")
    args = parser.parse_args(argv)

    decision = decide(tool=args.tool, amount=args.amount, domain=args.domain)
    if args.json:
        print(json.dumps(asdict(decision), indent=2))
    else:
        print(decision.verdict)
    return {"allow": 0, "approve": 0, "deny": 2}[decision.verdict]


if __name__ == "__main__":
    raise SystemExit(main())