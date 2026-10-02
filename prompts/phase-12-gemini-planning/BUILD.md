# BUILD — Phase 12 real AI planning on Gemini (NORMAL)

Type NORMAL. No siblings. OWN: `tests/test_llm_gemini*.py` (new). EXCEPTION (narrow): edit ONLY `src/runtime/planner.py::_plan_submit_tool` (+ anyREQ `strict` flag path in `llm_plan`) and `src/llm/router.py` (per-endpoint model/schema profile) — nothing else in those files. DO NOT TOUCH other files. Read-only: 07 REPORT (live probes transcript), 09 REPORT (schema-shape findings).

## Context (owner order: no fake AI — the model must really plan)
Today `--llm` on Gemini degrades: `MALFORMED_FUNCTION_CALL`, `completion_tokens: 0`, on the strict `submit_plan` schema (prime suspect per 09: pinned empty `args` object with `required: []`; sibling variants with `$defs` inlined also rejected). Fallback hides this. That ends now.

## Goal
`GEMINI_API_KEY` exported + `demo --llm` (and UI `--llm`) returns a REAL model-generated plan (`plan_source: llm:gemini/...`, no `fallback`), verified live.

## Deliverables
- Per-provider submit schema: keep strict for OpenAI endpoints; for Gemini (`generativelanguage`) send a Gemini-palatable shape (drop `strict`, inline `$defs`, no empty-required objects — experiment against the LIVE key, keep what the endpoint accepts; cite measured `finish_reason` per variant in REPORT).
- Router: per-endpoint profile (model name, schema mode); rotation/failover unchanged; key faults still by wording+status.
- Tests (offline-pinned): both schema variants validate; strict still enforced for OpenAI; fallback path still green when LLM errors.
- REPORT with the live transcript: `plan_source`, model name, tokens, attempts, and the 429-cooldown behavior if hit.

## Criteria
- Live (owner key, env-only): `make_plan(task, registry(), offline=False)` → `plan_source llm:gemini/*`, steps find→post, `finish_reason tool_calls` (or documented equivalent).
- `demo --llm` cold run → `plan: llm:gemini/*` in verdict line (NOT `heuristic(fallback…)`), still pass 8/8.
- Full suite green; no-key behavior byte-identical (heuristic, offline).

## Constraints
- No new deps; never log keys (redact); retry transient only (429/408/5xx + backoff/jitter per https://ai.google.dev/gemini-api/docs/troubleshooting). Honest: if Gemini cannot take the schema at all, prove it with 3+ variants and say so — do not fake a plan client-side.

## Order
Write `prompts/phase-12-gemini-planning/REPORT.md` (variants tried + live output, files changed, limits). Phase 13 (UI story) waits on this — the page must show a REAL model name.
