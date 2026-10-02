"""Executor: the only place a tool is called.

Rules that make the operator trustworthy:
- dispatch by manifest name only — an unknown tool can never run;
- args validated against the manifest JSON Schema before exec (trust boundary);
- a tool that returns {"ok": false} FAILED: tools report failure in the payload, not by raising;
- idempotent: a (tool, args) pair that already succeeded replays from the ledger
  instead of running again;
- every attempt is an append-only ledger row + redacted event before and after;
- a failing step never kills the run: the Adapt stage decides what happens next.

Phase 03 wraps this call site with its policy gate (allow|approve|deny).
"""

from __future__ import annotations

import re
from typing import Any, Callable, Mapping

from pydantic import BaseModel

from ..contracts.events import ACTOR_EXECUTOR, Event
from ..contracts.tools import ToolManifest, validate_args
from ..ledger.store import Ledger, idem_key
from .planner import Step

# "{{s1.latest.amount}}" -> the value the dependency recorded. The planner emits these instead of
# inventing a payload from the task text, so a write step can only post what a read step found.
_REF_RE = re.compile(r"^\{\{\s*([A-Za-z0-9_]+)((?:\.[A-Za-z0-9_]+)+)\s*\}\}$")


def payload_failed(result: Any) -> bool:
    """True when a tool returned an {ok: false} envelope. That is a failure, not a result."""
    return isinstance(result, dict) and result.get("ok") is False


def _resolve(value: Any, upstream: Mapping[str, "StepResult"]) -> Any:
    if isinstance(value, str):
        m = _REF_RE.match(value.strip())
        if m is None:
            return value
        node: Any = upstream[m.group(1)].result
        for part in m.group(2).lstrip(".").split("."):
            node = node[part] if isinstance(node, dict) else getattr(node, part)
        return node
    if isinstance(value, dict):
        return {k: _resolve(v, upstream) for k, v in value.items()}
    if isinstance(value, list):
        return [_resolve(v, upstream) for v in value]
    return value


def resolve_refs(args: dict[str, Any], upstream: Mapping[str, "StepResult"]) -> dict[str, Any]:
    """Concrete args for exec: every {{step.field}} placeholder read out of the dependency's result.

    Raises KeyError/AttributeError on a reference the upstream result does not carry — the caller
    records that as a failed step rather than posting a literal "{{...}}" to a money path.
    """
    return {k: _resolve(v, upstream) for k, v in args.items()}


class StepResult(BaseModel):
    """Outcome of one step attempt."""

    step_id: str
    tool: str
    status: str  # succeeded|failed|cached|skipped
    result: Any = None
    error: str | None = None
    idem_key: str = ""
    attempt: int = 1
    from_run: str | None = None

    @property
    def ok(self) -> bool:
        """True only when the step executed here and its payload is not an ok:false envelope."""
        return self.status == "succeeded" and not payload_failed(self.result)

    @property
    def resolved(self) -> bool:
        """The step ended well here or replayed a good outcome from the ledger: safe to depend on."""
        return self.status in ("succeeded", "cached") and not payload_failed(self.result)


class Executor:
    def __init__(
        self,
        ledger: Ledger,
        run_id: str,
        manifests: Mapping[str, ToolManifest],
        callables: Mapping[str, Callable[..., Any]],
        *,
        authorizer: Callable[[ToolManifest, dict[str, Any]], str] | None = None,
    ) -> None:
        self.ledger = ledger
        self.run_id = run_id
        self.manifests = dict(manifests)
        self.callables = dict(callables)
        self.authorizer = authorizer

    def emit(self, type: str, *, step_id: str | None = None, tool: str | None = None, **kw: Any) -> None:
        self.ledger.append_event(
            Event.new(self.run_id, type, actor=ACTOR_EXECUTOR, step_id=step_id, tool=tool, **kw)
        )

    def run_step(
        self,
        step: Step,
        seq: int,
        *,
        attempt: int = 1,
        replay: bool = True,
        upstream: Mapping[str, StepResult] | None = None,
    ) -> StepResult:
        try:
            step.args = resolve_refs(step.args, upstream or {})
        except (KeyError, AttributeError, TypeError) as exc:
            return self._record(step, seq, attempt, idem_key(step.tool, step.args), status="failed",
                                error=f"unresolved argument reference: {exc}")
        key = idem_key(step.tool, step.args)
        manifest = self.manifests.get(step.tool)
        if manifest is None:
            return self._record(step, seq, attempt, key, status="skipped",
                               error=f"tool {step.tool!r} is not in the manifest registry; nothing executed")

        errors = validate_args(manifest, step.args)
        if errors:
            return self._record(step, seq, attempt, key, status="skipped",
                               error="manifest schema violation: " + "; ".join(errors))

        if replay:
            prior = self.ledger.find_by_idem(key)
            if prior is not None:
                return self._record(step, seq, attempt, key, status="cached", result=prior.get("result"),
                                    from_run=prior.get("run_id"))

        decision = self.authorizer(manifest, step.args) if self.authorizer else "allow"
        if decision != "allow":
            self.emit("approval.requested", step_id=step.id, tool=step.tool,
                      payload={"risk": manifest.risk, "decision": decision})
            if decision == "deny":
                return self._record(step, seq, attempt, key, status="skipped", error="policy denied this tool")
            return self._record(step, seq, attempt, key, status="skipped",
                                error="blocked: approval required (no approval channel in Phase 01)")

        fn = self.callables.get(step.tool)
        if fn is None:
            return self._record(step, seq, attempt, key, status="skipped",
                               error=f"tool {step.tool!r} has a manifest but no callable; nothing executed")

        self.emit("step.started", step_id=step.id, tool=step.tool,
                  payload={"args": step.args, "risk": manifest.risk, "attempt": attempt})
        try:
            raw = fn(**step.args)
            result = raw.model_dump(mode="json") if hasattr(raw, "model_dump") else raw
            if payload_failed(result):
                # A tool reports failure in its payload; recording that as `succeeded` is what let
                # an ERP 422 read green and then replay as `cached`. Fail loudly instead.
                return self._record(step, seq, attempt, key, status="failed", result=result,
                                    error=result.get("error") or f"tool returned ok:false (status={result.get('status')})")
            return self._record(step, seq, attempt, key, status="succeeded", result=result)
        except Exception as exc:  # noqa: BLE001 - a tool failure is data, not a crash
            return self._record(step, seq, attempt, key, status="failed", error=f"{type(exc).__name__}: {exc}")

    def _record(
        self,
        step: Step,
        seq: int,
        attempt: int,
        key: str,
        *,
        status: str,
        result: Any = None,
        error: str | None = None,
        from_run: str | None = None,
    ) -> StepResult:
        row = {
            "idem_key": key,
            "run_id": self.run_id,
            "step_id": step.id,
            "seq": seq,
            "tool": step.tool,
            "args": step.args,
            "depends_on": step.depends_on,
            "status": status,
            "result": result,
            "error": error,
            "attempt": attempt,
        }
        self.ledger.append_step(row)
        res = StepResult(
            step_id=step.id,
            tool=step.tool,
            status=status,
            result=result,
            error=error,
            idem_key=key,
            attempt=attempt,
            from_run=from_run,
        )
        self.emit(
            {"succeeded": "step.succeeded", "cached": "step.cached", "failed": "step.failed", "skipped": "step.failed"}[status],
            step_id=step.id,
            tool=step.tool,
            payload={"status": status, "attempt": attempt, "result": result},
            error=error,
        )
        return res
