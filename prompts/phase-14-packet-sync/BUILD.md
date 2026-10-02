# BUILD — Phase 14 packet sync (NORMAL, docs-only, pre-record)

Type NORMAL. No siblings. EXCEPTION (docs only): edit ONLY `README.md`, `SUBMISSION.md`, `docs/USER-TEST.md`, `demo/video-script.md` (numbers + --llm truth + UI run-order). DO NOT TOUCH code/tests. Read-only: 12/13 REPORTs (source of truth), 10 REPORT (role line).

## Context
Suite is 156; packet still says 133 in README:253, SUBMISSION:13, USER-TEST ~7s timing; step 13 + F2-era claims describe --llm as fallback (12 proved live planning); SUBMISSION run-order never mentions the UI page (11's parked item).

## Goal
Record-ready packet: zero stale numbers, --llm told truthfully, reviewer told to open the UI first.

## Deliverables
1. `133→156` (+`~7s→~16s`) everywhere granted (grep to prove zero stale, allowing labeled historical appendices).
2. USER-TEST step 13 rewritten: --llm live-plans on Gemini (model named, temp:0, ~30–60s/call warning, fallback conditions) + 05/FIX-2 note if still open.
3. SUBMISSION "run in order": UI page first (`python3 -m src.ui.app --port 0`), terminal second; keep 10's role line byte-identical in meaning.
4. REPORT with grep proofs + one honest line on which model the video take should use (flash speed vs gemma proof — measure ONE `GEMINI_MODEL=gemini-2.5-flash` cold `--llm` take for timing; report, don't reshoot).

## Criteria
- `grep -rn "133 passed\|133 tests" README.md SUBMISSION.md docs/ demo/` → empty (or labeled-history only).
- Every --llm sentence matches 12's transcript. Full suite untouched (no code changes to break it).

## Order
Write `prompts/phase-14-packet-sync/REPORT.md`. Out of scope: code, schema, F3 (05/FIX-2 file already exists — run it or consciously defer).
