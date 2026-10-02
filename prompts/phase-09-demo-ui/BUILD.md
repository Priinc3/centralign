# BUILD — Phase 09 demo UI (NORMAL, evaluator-visible)

Type NORMAL (after 08 ✅). No siblings. OWN files (new dir, no clash — 05 explicitly skipped `src/ui/*`): `src/ui/*`, `tests/test_ui*.py`. DO NOT TOUCH anything else (engine frozen; 05/FIX-2 may still land `src/cli/main.py` — coordinate via REPORT note, never edit it). Read-only: `src/runtime/loop.py`, `src/ledger/*`, `src/reliability/hitl.py`, `demo/run.sh`.

## Context + end goal
Owner request (explicit, overrides 05's ponytail skip): evaluators should SEE the run, not read terminal scroll. Same invoice demo, visible.

## Goal
`python3 -m src.ui.app` → localhost page showing task → live steps (poll) → approval button → verdict + evidence + ERP row. Zero new deps (stdlib `http.server` + vanilla JS `fetch`).

## Deliverables (OWN only)
- `src/ui/app.py` (stdlib server: `GET /` page, `POST /api/run` starts invoice task on scratch sim/ledger, `GET /api/state` ledger steps+verdict, `POST /api/approve` grants pending request; binds 127.0.0.1, free port, prints URL).
- `src/ui/index.html` (one page: Run button, step list w/ status icons, approval card w/ Approve button, verdict banner `pass 8/8 replayed=N`, evidence `<details>` JSON, ERP row line; auto-refresh 500ms; plain words, no framework).
- `tests/test_ui_offline.py` (server up, run→approve→pass via HTTP, no browser needed; port cleanup).
- `docs`-free: add UI section to REPORT only (README update waits for 08-style refresh if numbers move).

## Criteria (must run)
- `python3 -m src.ui.app --port 0` → open printed URL → Run → Approve → `pass 8/8`, ERP count 1, evidence visible; second Run shows `replayed=2`.
- `python3 -m pytest tests/test_ui_offline.py -q` + full suite green; `python3 -m src.security.scan` 0 findings (page leaks no keys).
- Localhost only (no 0.0.0.0); no key required; works with no playwright.

## Constraints
- Stdlib only; reuse `run_task(authorizer=hitl.authorizer)`, ledger reads, evidence JSON. Secure: deny-by-default maintained (button approves named request only), redact before serving. Fast: first paint <1s, poll 500ms.

## Order
Write `prompts/phase-09-demo-ui/REPORT.md` (files changed, cmds+raw output incl. screenshot description, limits). Video note: re-record optional 20s UI beat after.
