"""Frozen contract: event envelope (append-only audit log).

Every runtime/tool/memory action is one Event, written to the ledger before and
after the action, and mirrored into the evidence bundle.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

EventType = Literal[
    "run.started",
    "run.stage",
    "step.planned",
    "step.started",
    "step.succeeded",
    "step.failed",
    "step.cached",
    "approval.requested",
    "approval.granted",
    "approval.denied",
    "verify.checked",
    "run.completed",
    "run.failed",
    "log",
]

ACTOR_SYSTEM = "system"
ACTOR_PLANNER = "planner"
ACTOR_EXECUTOR = "executor"
ACTOR_VERIFIER = "verifier"
ACTOR_TOOL = "tool"
ACTOR_OPERATOR = "operator"

_SECRET_KEY_RE = re.compile(
    r"\b(pass(word|phrase)?|secret|token|api[-_]?key|authorization|auth[-_]?header|cookie|bearer|credential"
    r"|session[-_]?id|private[-_]?key|access[-_]?key|refresh[-_]?token)\b",
    re.IGNORECASE,
)
REDACTED = "[REDACTED]"
# ponytail: pattern-based redaction, not a real secret scanner; Phase 06 hardens.


def redact(value: Any, _depth: int = 0) -> Any:
    """Mask secret-looking keys and inline `Bearer <tok>` / `sk-...` values, recursively."""
    if _depth > 12:
        return "[TRUNCATED]"
    if isinstance(value, dict):
        return {
            k: (REDACTED if _SECRET_KEY_RE.search(str(k)) else redact(v, _depth + 1))
            for k, v in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [redact(v, _depth + 1) for v in value]
    if isinstance(value, str):
        value = re.sub(r"(?i)bearer\s+\S+", f"Bearer {REDACTED}", value)
        value = re.sub(r"\bsk-[A-Za-z0-9_\-]{8,}", REDACTED, value)
        return value
    return value


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class Event(BaseModel):
    """One immutable audit record."""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    seq: int = Field(ge=0, description="Monotonic per run_id; assigned by the ledger")
    type: EventType
    ts: str = Field(default_factory=utc_now)
    actor: str = ACTOR_SYSTEM
    step_id: str | None = None
    tool: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None

    @classmethod
    def new(
        cls,
        run_id: str,
        type: EventType,
        *,
        actor: str = ACTOR_SYSTEM,
        step_id: str | None = None,
        tool: str | None = None,
        payload: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> Event:
        """Build an already-redacted, seq-less event (ledger assigns seq on append)."""
        return cls(
            run_id=run_id,
            seq=0,
            type=type,
            actor=actor,
            step_id=step_id,
            tool=tool,
            payload=redact(payload or {}),
            error=redact(error) if error else None,
        )

    def to_contract(self) -> dict[str, Any]:
        return self.model_dump(mode="json")
