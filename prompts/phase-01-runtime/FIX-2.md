# FIX-2 — Phase 01 runtime (wire Phase 04 HELP-1..5)

Scope locked: `src/runtime/loop.py`, `src/ledger/store.py`, `src/ledger/evidence.py`, `tests/test_runtime_smoke.py:262` only. DO NOT touch `src/reliability/*`, `src/verifier/*`, tools/memory/policy. Contracts frozen (no shape change). Apply REPORT `phase-04-reliability/HELP-1..5` verbatim except note below; update REPORT.md append FIX-2 section.

## HELP-1 — retry+replan into loop (P0)
`src/runtime/loop.py`: import `RetryPolicy, run_step_with_retry` + `replan`; `MAX_ATTEMPTS=1`, `POLICY=RetryPolicy()`; inside `execute()` replace `executor.run_step` with `run_step_with_retry(...)`; after sweep re-derive first `failed` and call `replan(...)`, append `run.stage=replan` event, execute replanned steps. Note: REPORT says loop will then make 0 attempts on 422 (classify fatal) vs old 1 retry — accept (fewer duplicate posts).

## HELP-2 — F3 attempt bump (P0)
`src/ledger/store.py:126 append_step`: SELECT MAX(attempt) for (run_id,step_id); if incoming attempt ≤ max, bump to max+1. Update `tests/test_runtime_smoke.py:262` (was `pytest.raises(IntegrityError)`) to assert bump. Unblocks 04 xfail (must XPASS after).

## HELP-3 — plan_source in evidence (P0)
`src/ledger/evidence.py:52` add `"plan_source": run.get("plan_source")`; `loop.py:381` pass `plan_source` alongside `run` dict. (`state.json` already has it.)

## HELP-4 — verify delegates (P0, correctness)
`src/runtime/loop.py:139-239 verify()`: replace 100-line inline copy with lazy `from ..verifier.checks import verify as _verify; return _verify(...)` (lazy = circular otherwise). Same signature/names/blocked semantics. Fixes fail-OPEN `audit_trail_complete` + cached miscount.

## HELP-5 — HITL gate (P1)
`run_task`: add optional `authorizer=None`, pass to `Executor(..., authorizer=authorizer)`. No existing caller changes. Enables Phase 05 CLI to pass `hitl.authorizer`.

## Verify-with (must paste raw output)
- `python3 -m pytest tests/ -q` (04 xfail must XPASS → suite green, update strict marker if needed).
- Cold→warm ERP run + stub-422 run + `plan_source` in evidence `run` block + resume + HITL pending/approve (use REPORT verify steps §Verify steps).
- Append FIX-2 section to `prompts/phase-01-runtime/REPORT.md`; COMM INFO; STATUS 01 DONE.
