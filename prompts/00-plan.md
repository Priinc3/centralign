# 00-plan — CentrAlign AI Operator (Founding/Intern unified)

## Goal (1-line DONE)
Reliable AI employee that turns `Find latest invoice from Company X, extract amount+due, enter into internal system, tell me when done` into verified completed work with evidence, approvals on risk, and audit trail — demoable offline in <60s setup.

## Vision (unique, quality>quantity)
**Contract-bound autonomy + evidence-first verification.** LLM plans only; deterministic code executes. Every run produces a verifiable Plan DAG → idempotent tool calls → independent verifier predicates → evidence bundle (JSON+logs). No silent mock autonomy: if a tool didn't run, REPORT says so. Narrow invoice domain done genuinely > broad fake.

## Stack (searched, minimal deps)
- Python 3.11+, stdlib-first; deps only: `openai`, `playwright` (chromium), `pydantic`, `pyyaml`, `pytest` — nothing else without CEO approval.
- LLM: OpenAI-compatible tool-calling with strict structured outputs; offline heuristic planner fallback when no key (demo never blocks on key).
  - https://developers.openai.com/api/docs/guides/function-calling
  - https://developers.openai.com/api/docs/guides/structured-outputs
- Browser: Playwright Python sync API, Chromium only, URL allowlist, auto-wait (no sleep loops).
  - https://playwright.dev/python/docs/library
  - https://playwright.dev/python/docs/intro
- Memory/audit: SQLite WAL mode, single-writer queue, JSON audit table.
  - https://www.sqlite.org/wal.html
- Sim company app: stdlib `http.server` + SQLite (no Flask/FastAPI — ponytail ladder rung 3).

## Phases (frozen types)
| Phase | Slug | Type | OWN files (exclusive) | Goal |
|---|---|---|---|---|
| 01 | runtime | PARALLEL:G1 | `src/runtime/*`, `src/ledger/*`, `src/contracts/*` (defines contract) | Core loop Goal→Understand→Plan→Execute→Observe→Adapt→Verify→Complete + state + evidence bundle |
| 02 | tools | PARALLEL:G1 | `src/tools/*`, `sim_app/*`, `data/seed/*` | Idempotent tools: browser (allowlisted), files, invoice parser, sim-ERP client; seed invoices |
| 03 | memory | PARALLEL:G1 | `src/memory/*`, `src/policy/*`, `context/*` | Company memory (SQLite), YAML policies/permissions, risk-tiered approval gate |
| 04 | reliability | NORMAL | `src/reliability/*`, `src/verifier/*`, `tests/test_reliability*` | Retries/backoff, replan, verifier predicates, HITL CLI, checkpoint/resume |
| 05 | demo-ux | NORMAL | `src/cli/*`, `src/ui/*`, `demo/*`, `tests/test_demo*` | Beautiful fast CLI (+tiny web view), seeded invoice demo <60s, <1s feedback |
| 06 | hardening | NORMAL | `src/security/*`, `README.md`, `SUBMISSION.md`, `tests/test_security*` | Secret redaction, IDOR/allowlist guards, audit export, README+video script+limits |

Parallel map G1: goal=foundations in parallel; members=01,02,03; shared contract (frozen)=`src/contracts/` (ToolManifest, Event envelope, Memory API, Verdict schema — owned by 01, read-only for 02/03); comm=`prompts/parallel-G1/`; integration TEST=`prompts/batch-B1-TEST.md` (invoice E2E + contract clash check). Why safe: disjoint OWN files, contract frozen, integration point named (`run_task("invoice intake")`).

## Batches
- B1 = G1 (01+02+03) → one batch TEST.
- B2 = 04+05+06 (3 NORMAL) → one batch TEST.
- Final = `prompts/final-TEST.md` cross-batch regression + goal acceptance.

## DONE condition
All batches ✅ VERIFIED (0 🔴/🟠, 🟡 fixed or WAIVED) + offline demo passes + evidence bundle verifies + README+video ready for Oct 4 5:30 PM IST form.
