"""Retry policy: exponential backoff with jitter, and retryable-vs-fatal triage.

The triage is the load-bearing half. A 422 from the ERP is a rejected payload: re-sending
it three times burns the budget, delays the failure report, and on a non-idempotent tool
risks a second side effect. Only a transport fault or an explicit 408/425/429/5xx earns
another attempt. Everything unrecognised is fatal — deny by default, including the retry.

Deterministic by construction: the jitter is seeded per (seed, attempt) rather than drawn
from a shared RNG, so a test sees the same delay every run and a resumed run does not
inherit a half-spent random state.

Wiring: `run_step_with_retry` is a drop-in for `Executor.run_step` (see REPORT HELP-1).
"""

from __future__ import annotations

import random
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable

RETRYABLE = "retryable"
FATAL = "fatal"

MAX_ATTEMPTS = 3  # 1 initial call + 2 retries
BASE_DELAY = 0.5
MAX_DELAY = 8.0

# The server is busy or briefly broken, not the request.
RETRYABLE_STATUS = frozenset({408, 425, 429, 500, 502, 503, 504})
# Transport faults, as the tools word them (`erp_tool._request` sets status=None for these).
RETRYABLE_TEXT = re.compile(
    r"timed?[\s-]?out|timeout|connection (?:reset|refused|aborted|closed)"
    r"|unreachable|temporarily unavailable|try again|\blater\b"
    r"|bad gateway|gateway time-?out|service unavailable|server overloaded",
    re.IGNORECASE,
)
# Answers a retry cannot fix. Checked before the retryable text so "422: invalid amount"
# never reaches the retry branch on the strength of one stray word.
FATAL_TEXT = re.compile(
    r"schema violation|not in the manifest registry|no callable|policy denied"
    r"|unresolved argument reference|unauthori[sz]ed|forbidden|not found"
    r"|invalid|not a number|missing required field|validation",
    re.IGNORECASE,
)
# `status=422` (executor payload envelope) or `HTTP Error 422:` (urllib).
_STATUS_RE = re.compile(r"\bstatus\s*[=:]\s*(\d{3})\b|\bHTTP(?: Error)?\s+(\d{3})\b", re.IGNORECASE)


def status_of(payload: Any) -> int | None:
    """The HTTP status a tool envelope carries, if any. `{ok: false, status: 422}` -> 422."""
    if isinstance(payload, dict):
        status = payload.get("status")
        if isinstance(status, int) and not isinstance(status, bool):
            return status
    return None


def classify(*, error: str = "", status: int | None = None) -> str:
    """`retryable` or `fatal`. Order is fixed: explicit status beats prose, prose beats default.

    An explicit 4xx is fatal even if the message mentions a timeout — the server answered, so
    re-sending the identical request would get the identical answer.
    """
    if status is None:
        m = _STATUS_RE.search(error or "")
        status = int(next(g for g in m.groups() if g)) if m else None
    if status is not None:
        if status in RETRYABLE_STATUS:
            return RETRYABLE
        if 400 <= status < 500:
            return FATAL
    text = error or ""
    if FATAL_TEXT.search(text):
        return FATAL
    if RETRYABLE_TEXT.search(text):
        return RETRYABLE
    return FATAL  # unrecognised error: do not spend retries on it


def is_retryable(result: Any) -> bool:
    """True when a failed StepResult is worth another attempt."""
    return (
        getattr(result, "status", None) == "failed"
        and classify(error=getattr(result, "error", "") or "",
                     status=status_of(getattr(result, "result", None))) == RETRYABLE
    )


@dataclass(frozen=True)
class RetryPolicy:
    """Exponential backoff with bounded jitter. `sleeper` is injected so tests never wait."""

    max_attempts: int = MAX_ATTEMPTS
    base_delay: float = BASE_DELAY
    max_delay: float = MAX_DELAY
    jitter: float = 0.5  # fraction of the delay that is randomised, so N clients desynchronise
    seed: int | None = None
    sleeper: Callable[[float], None] = field(default=time.sleep)

    def delay_for(self, attempt: int) -> float:
        """Seconds to wait before `attempt`+1 (1-based `attempt`).

        Seeded per (seed, attempt): reproducible, and stateless, so two callers with the same
        policy do not share an RNG. The jitter multiplies the delay, so the wait stays inside
        [0.75x, 1.25x] of the capped value for the default 0.5.
        """
        raw = min(self.max_delay, self.base_delay * 2 ** (max(attempt, 1) - 1))
        if self.jitter <= 0:
            return raw
        rng = random.Random(f"{self.seed}:{attempt}")
        return raw * (1 - self.jitter / 2 + self.jitter * rng.random())


DEFAULT_POLICY = RetryPolicy()


def run_step_with_retry(
    executor: Any,
    step: Any,
    seq: int,
    *,
    attempt: int = 1,
    policy: RetryPolicy = DEFAULT_POLICY,
    upstream: dict[str, Any] | None = None,
    replay: bool = True,
) -> Any:
    """`executor.run_step`, retried with backoff while the failure looks transient.

    Each attempt is its own `run_step` call, so each lands as its own append-only ledger row
    keyed (run_id, step_id, attempt) and its own event — nothing is rewritten. The happy path
    makes exactly one call and never touches `sleeper`.

    Returns the last StepResult regardless of why it ended; it never raises for a tool
    failure, because a tool failure is data, not a crash.
    """
    result = executor.run_step(step, seq, attempt=attempt, replay=replay, upstream=upstream)
    while is_retryable(result) and attempt < policy.max_attempts:
        delay = policy.delay_for(attempt)
        executor.emit(
            "log",
            step_id=step.id,
            tool=step.tool,
            payload={
                "stage": "retry",
                "attempt": attempt,
                "next_attempt": attempt + 1,
                "delay_s": round(delay, 3),
                "classify": RETRYABLE,
                "reason": result.error,
            },
        )
        policy.sleeper(delay)
        attempt += 1
        result = executor.run_step(step, seq, attempt=attempt, replay=replay, upstream=upstream)
    if is_retryable(result):
        executor.emit(
            "log",
            step_id=step.id,
            tool=step.tool,
            payload={"stage": "retry_exhausted", "attempts": attempt, "reason": result.error},
        )
    return result


def main(argv: list[str] | None = None) -> int:
    """`python -m src.reliability.retry "<error text>" [status]` — triage one failure, no run."""
    import argparse

    ap = argparse.ArgumentParser(prog="python -m src.reliability.retry", description=__doc__)
    ap.add_argument("error", nargs="?", default="", help="error string to classify")
    ap.add_argument("status", nargs="?", type=int, default=None, help="HTTP status, if known")
    args = ap.parse_args(argv)
    print(classify(error=args.error, status=args.status))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())