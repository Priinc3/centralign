"""Frozen contract: verifier predicates + verdict.

Phase 04 (src/verifier/*) implements predicate evaluators; it must emit these
shapes so the evidence bundle stays comparable across runs.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .events import utc_now

PredicateKind = Literal["tool_result", "ledger", "event_log", "artifact", "policy", "custom"]
VerdictStatus = Literal["pass", "fail", "blocked"]


class Predicate(BaseModel):
    """One checkable statement about a run, independent of how it was produced."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    kind: PredicateKind
    statement: str = Field(min_length=1, description="Human-readable claim, e.g. 'erp.post created exactly 1 row'")
    expected: Any = None
    actual: Any = None
    passed: bool = False
    weight: int = Field(default=1, ge=0)
    detail: str | None = None
    evidence_ref: str | None = Field(default=None, description="Pointer into the bundle, e.g. steps/s3/result")


class Verdict(BaseModel):
    """Result of the Verify stage: pass only when every required predicate passed."""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    status: VerdictStatus = "blocked"
    predicates: list[Predicate] = Field(default_factory=list)
    summary: str = ""
    verified_at: str = Field(default_factory=utc_now)
    evidence_ref: str | None = None

    @property
    def ok(self) -> bool:
        return self.status == "pass"

    @property
    def failed(self) -> list[Predicate]:
        return [p for p in self.predicates if not p.passed]

    @classmethod
    def from_predicates(
        cls,
        run_id: str,
        predicates: list[Predicate],
        *,
        blocked: bool = False,
        summary: str | None = None,
        evidence_ref: str | None = None,
    ) -> Verdict:
        failed = [p for p in predicates if not p.passed]
        status: VerdictStatus = "blocked" if blocked else ("fail" if failed else "pass")
        text = summary or (
            f"{len(predicates) - len(failed)}/{len(predicates)} predicates passed"
            if predicates
            else "no predicates evaluated"
        )
        return cls(
            run_id=run_id,
            status=status,
            predicates=predicates,
            summary=text,
            evidence_ref=evidence_ref,
        )

    def to_contract(self) -> dict[str, Any]:
        return self.model_dump(mode="json")
