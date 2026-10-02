# BUILD — Phase 01 runtime (G1)

You are Phase 01 (G1). Siblings running now: [02-tools: src/tools/*, sim_app/*], [03-memory: src/memory/*, src/policy/*, context/*]. Your OWN files: `src/runtime/*`, `src/ledger/*`, `src/contracts/*`. DO NOT TOUCH siblings' OWN files. Shared read-only: none yet (you define contract). Comm folder: `prompts/parallel-G1/` (create COMM.md+STATUS.md from stub below if missing).

## Context + end goal
See `prompts/00-plan.md` goal: invoice intake → verified work + evidence. You own the loop everyone plugs into.

## Goal
Deterministic operator loop: Goal→Understand→Plan→Execute→Observe→Adapt→Verify→Complete with Plan DAG (pydantic), state checkpoint (JSON), evidence bundle.

## Deliverables (OWN files only)
- `src/contracts/` : `tools.py` (ToolManifest w/ JSON Schema + risk tier), `events.py` (envelope), `verdict.py` (Verifier predicates schema) — FROZEN once written, others depend on it.
- `src/runtime/loop.py`, `planner.py` (LLM tool-call + offline heuristic fallback), `executor.py` (dispatch via manifest only).
- `src/ledger/store.py` (SQLite WAL append-only runs/steps), `evidence.py` (bundle writer).
- `tests/test_runtime_smoke.py` (fake tool, proves loop+evidence without LLM key).

## Criteria (must run)
- `python -m pytest tests/test_runtime_smoke.py -q` passes.
- `python -m src.runtime.loop --task "demo" --offline` writes `runs/<id>/evidence.json` with steps+verdict.
- No network needed for offline path; <2s smoke.

## Constraints (verified)
- OpenAI tool-calling strict mode only (`strict:true`, required+additionalProperties:false): https://developers.openai.com/api/docs/guides/function-calling
- Structured outputs for plan DAG: https://developers.openai.com/api/docs/guides/structured-outputs
- SQLite WAL: `PRAGMA journal_mode=WAL; synchronous=NORMAL; busy_timeout=5000`: https://www.sqlite.org/wal.html
- Quality: stdlib-first, one impl per interface, idempotent executor, secrets never logged. Fast: sync code, no sleeps, minimal deps.

## Parallel rules
- COMM.md: `## 01 HH:MM — <25 words` + tag INFO|HELP|DECISION|BLOCKED; no dumps, link REPORT; <60 lines.
- STATUS.md table `| Phase | State | Updated | Doing now | Need |`; update ONLY your row; State ACTIVE|BLOCKED|DONE.
- Check COMM+STATUS at start + before REPORT. Need shared change → post HELP, wait. Never silent-edit others' files = 🔴 fail.
- Stub if creating:
  COMM.md → `# G1 comm\n## 01 <time> — started, contracts draft [INFO]\n`
  STATUS.md → `| Phase | State | Updated | Doing now | Need |\n|---|---|---|---|---|\n| 01 | ACTIVE | <time> | contracts+loop | — |\n`

## Order
Write `prompts/phase-01-runtime/REPORT.md` with: files changed, cmds+raw output, verify steps, limits, help needed, BLOCKED BY if stalled.
