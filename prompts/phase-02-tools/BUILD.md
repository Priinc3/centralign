# BUILD — Phase 02 tools + sim app (G1)

You are Phase 02 (G1). Siblings running now: [01-runtime: src/runtime/*, src/ledger/*, src/contracts/*], [03-memory: src/memory/*, src/policy/*, context/*]. Your OWN files: `src/tools/*`, `sim_app/*`, `data/seed/*`. DO NOT TOUCH: 01/03 OWN files. Shared read-only: `src/contracts/` (ToolManifest, Event envelope — wait for 01's COMM announce; if missing, stub locally but don't write there, post HELP). Comm folder: `prompts/parallel-G1/`.

## Context + end goal
See `prompts/00-plan.md`. You give the operator real hands: browser+files+ERP. Narrow invoice domain, genuinely working.

## Goal
Idempotent, allowlisted tools + tiny sim ERP + seed invoices for offline demo.

## Deliverables (OWN files only)
- `src/tools/manifest_registry.py` (loads manifests matching contracts), `browser_tool.py` (Playwright sync, chromium, allowlist only, auto-wait), `files_tool.py` (sandboxed to `data/`), `invoice_tool.py` (regex+pdf text extract, amount/due), `erp_tool.py` (POST to sim ERP, idempotency-key).
- `sim_app/server.py` (stdlib http.server, `/invoices` POST/GET, SQLite store), `sim_app/schema.sql`.
- `data/seed/invoices/` (3 PDFs/text: Company X latest + 2 distractors), `data/seed/expected.json`.
- `tests/test_tools_smoke.py` (files+invoice parse+ERP roundtrip, no LLM).

## Criteria (must run)
- `python sim_app/server.py --port 8901 & python -m pytest tests/test_tools_smoke.py -q` passes.
- Browser tool with `ALLOWLIST=localhost,example.com` blocks `evil.com` (test asserts).
- Invoice parse extracts amount+due from seed X within ±0 error; ERP POST idempotent (double-POST = 1 row).

## Constraints (verified)
- Playwright sync API, chromium launch, auto-wait, no `time.sleep`: https://playwright.dev/python/docs/library ; install: https://playwright.dev/python/docs/intro
- Tools validate args via manifest JSON Schema before exec; risk tier from contract; destructive=confirm path.
- Quality: smallest working tools, no framework for sim app (stdlib). Fast: lazy browser launch, reuse context. Secure: sandbox `data/`, URL allowlist, no creds in code.

## Parallel rules
COMM.md `## 02 HH:MM — <25 words` + INFO|HELP|DECISION|BLOCKED; STATUS.md update ONLY your row. Check COMM+STATUS at start + before REPORT. Need contract change → HELP in COMM, wait for CEO FIX. Ownership violation = 🔴.
Stub if creating folder (same as 01): add row `| 02 | ACTIVE | <time> | tools+simapp | waiting contracts? |`.

## Order
Write `prompts/phase-02-tools/REPORT.md` with files changed, cmds+raw output, verify steps, limits, help needed, BLOCKED BY if waiting on 01.
