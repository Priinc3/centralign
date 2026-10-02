# VERIFY — Phase 04 reliability — ✅ VERIFIED (after 01/FIX-2)

Batch B2-part: VERIFIED. FIX-2 applied HELP-1..5, suite 83 passed/1 skipped (was 82+xfail; xfail now real pass).

## Proof
- Cold `succeeded/succeeded` → warm `cached/cached`, 1 ERP row; `each_success_has_evidence 2/2`, `audit_trail_complete 3/3` (were 0/2 fail-OPEN).
- Downed ERP: 6 attempts (3+3 replan) with 0.401/1.123s backoff, `plan=replan:heuristic`, attempts 4-6 via HELP-2 bump, rc=1 fail; 422 stub: 1 call (fatal, 0 retry), replan refused.
- `plan_source` in evidence `run` (`heuristic` / `replan:heuristic`); resume `failed→cached/succeeded`, ERP count 1; HITL block→approve→pass with pending line intact + closed appended; empty→blocked rc=1.
- Ownership: FIX-2 touched `src/runtime/loop.py`, `src/ledger/*`, smoke tests only; no contract/shape change (one optional key).

## Findings (0 🔴/🟠)
- 🟡 carried to 05: 6-attempt cost on downed service; `state.json` pre-replan stale; `adapt()` unreachable; thread-sleep backoff; `authorizer=None` default (05 wires CLI).
- Deviation accepted: `replan` guarded on failure≠None; `set_stage` around replan; 2 stale test premises moved with behavior.

## Goal check
Reliability on hot path. Open Phase 05.
