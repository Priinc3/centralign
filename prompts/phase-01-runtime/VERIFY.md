# VERIFY — Phase 01 runtime (G1) — ✅ VERIFIED (after FIX-1)

Batch B1 verdict: ✅ VERIFIED. Second TEST-RESULT (2026-10-02): PASS — invoice intake E2E works offline.

## Proof
- Suite 50 passed/1 skipped (was 13→17 runtime tests + G1 siblings). Happy loop cold-ledger `succeeded/succeeded` 8/8 predicates; warm-ledger `cached/cached` replay correct. E1 empty→`blocked` rc=1 "No task given". E2 double-submit rows=1. E3 offline 0.15s heuristic. Security 6/6 + redaction positive control. `ok:false→failed`, never replayed green (ledger rows `failed/failed`).
- COMM 37 lines (<60, no dumps); STATUS: 01 DONE 12:45, 02 DONE, 03 DONE (03 "NAME_RE needs dots" stale — dotted validated `erp.post→erp_post`, no action). Ownership held (FIX-1 touched runtime/ledger/tests only).

## Findings carried (0 🔴/🟠, 4 🟡 WAIVED to B2 with owner)
- 🟡 F1-warm-pass (replay looks like live pass) → WAIVED: correct idempotent behavior; follow-up Phase 05 CLI prints `replayed=N`.
- 🟡 F2-dirty-sim-DB → WAIVED: test hygiene; follow-up B2 TEST uses scratch `--db`.
- 🟡 F3 IntegrityError on same (run,step,attempt) re-record → WAIVED to Phase 04 (owns retries/replay).
- 🟡 F4 `plan_source` stdout-only → WAIVED to Phase 04 (add to evidence `run` block).
- 🟡 F5/F6 TEST-DOC probes → WAIVED: fixed in batch-B1-TEST.md v2 except `run_step(step,seq)`+envelope shape noted; B2 TEST uses corrected forms.

## Goal check
Moves end goal forward: offline invoice E2E genuinely passes with evidence. B1 closed.
