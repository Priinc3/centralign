# VERIFY — Phase 07 user acceptance — NEEDS-FIX (1 one-liner → 05/FIX-2)

OWN PASS proven: browser SKIP rc=0 + venv PASS 1.7s w/ screenshot; runbook steps re-verified cold; 127 passed/1 skipped; scan 0; router live-proven (invalid→real failover, 429 cooldown, redaction).

## Findings
- 🔴 F1 key pasted in chat — USER ACTION: rotate in AI Studio now. Tree clean (scan proves). Not code-blockable.
- 🟠 F2 Gemini rejects strict plan schema (MALFORMED_FUNCTION_CALL, strict and non-strict) — fallback honest (`heuristic(fallback…)`, still pass 8/8), documented step 13. WAIVED→Phase 08 optional (per-provider schema, planner-owned, post-submit): submission core is offline autonomy, unaffected.
- 🟠 F3 `run` gates LLM on OPENAI_API_KEY only; Gemini-only owner never reaches router via `run` — FIX in `phase-05-demo-ux/FIX-2.md` (one line + test). Blocks 07 close-out.
- 🟡 F4 400-key-fault wording — fixed in router + pinned test. F5 canary — fixed. F6 doc drift (114→127) — WAIVED: USER-TEST.md carries current numbers; refresh README/SUBMISSION/video-script at submit time.

## Goal check
Stalled only on F3 one-liner. F1 needs the human, not a phase.
