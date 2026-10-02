# BUILD — Phase 07 user acceptance (NORMAL, human-run)

Type NORMAL (after Final ✅). No siblings. OWN files (new dirs, no clash): `docs/USER-TEST.md`, `scripts/browser_check.py`, `src/llm/*`, `tests/test_llm_router*.py`. EXCEPTION (CEO-granted, narrow): you may edit ONLY the LLM-client construction + call in `src/runtime/planner.py::llm_plan` to route through `src.llm.router` (nothing else in that file). DO NOT TOUCH anything else. Read-only: `demo/run.sh`, `demo/script.md`, `demo/video-script.md`, `README.md`, all REPORTs/VERIFYs, `prompts/final-TEST-RESULT.md`.

## Context + end goal
Technical gates all green (115 tests, scans, demos). The owner now runs everything by hand with the builder on call. You produce the follow-along runbook + the browser verification script so the human verifies every claim live, including opening a real browser.

## Goal
A non-engineer-readable runbook the owner executes top-to-bottom with zero surprises, a scripted browser check of the sim portal (owner confirmed: install Playwright + Chromium and drive it), plus a multi-key LLM router (owner: Gemini keys rate-limit, so rotate + failover).

## Extra deliverable — `src/llm/router.py` (verified providers)
- Keys from env: `GEMINI_API_KEY`, `GEMINI_API_KEY_2..N` (any count), plus optional `OPENAI_API_KEY*` as fallback endpoints. Never log key material (reuse `contracts.events.redact`).
- Gemini via OpenAI-compatible endpoint `https://generativelanguage.googleapis.com/v1beta/openai/` with the existing `openai` client (https://ai.google.dev/gemini-api/docs/openai). No new SDK dependency.
- Rotation: round-robin across healthy keys; on `429 RESOURCE_EXHAUSTED` / 5xx mark key cooled-down and fail over to next (https://ai.google.dev/gemini-api/docs/troubleshooting — backoff+jitter, retry transient only, max attempts). 400/401/403 never retried (bad key/syntax).
- `tests/test_llm_router_keys.py`: rotation order, 429 failover, no-retry on 401, redaction of keys in logs. All offline (stubbed transport).
- Runbook gets a `--llm` step marked OPTIONAL (needs ≥1 key) + key-setup section (Google AI Studio link, `.env` never committed).

## Deliverables (OWN only)
- `docs/USER-TEST.md`: prereqs (python>=3.11, pip install -r requirements.txt, optional: `pip install playwright && python -m playwright install chromium`, optional `OPENAI_API_KEY`), API table (what needs a key: ONLY live-LLM planning; everything else offline — no other APIs, no real creds ever), 12-step run (doctor → cold demo → append replay → empty → downed-ERP fail → resume → approve drill → scan → suite → browser portal → evidence read → video beats), each step with exact cmd + expected output block + "if you see X instead, do Y" + tick box. Include pre-submit checklist (video URL, GitHub URL, form fields).
- `scripts/browser_check.py`: Playwright sync, chromium headless, goto sim `/portal` on a scratch sim (spawns own server like demo/run.sh), assert title + 3 seed invoices listed, screenshot to scratch, allowlist-negative (`evil.com` refused without launching). Skips cleanly with plain words when playwright absent. No new deps beyond playwright (optional import).
- Both docs state API needs up front: none required; `OPENAI_API_KEY` only to also prove `--llm` path; browser only if playwright installed.

## Criteria (must run)
- `python3 scripts/browser_check.py` → PASS with playwright, clean SKIP without (rc=0 both, different message).
- Follow runbook §1–3 on a cold machine path (fresh /tmp): every expected-output block matches; list any mismatch as a finding.
- `python3 -m pytest tests/ -q` stays green.

## Constraints
- https://playwright.dev/python/docs/library (sync API, auto-wait, no sleeps).
- Never ask for real company creds; sandbox `data/`; localhost only. Fast: browser check <30s.

## Order
Write `prompts/phase-07-user-acceptance/REPORT.md` with files changed, cmds+raw output (with AND without playwright if possible), findings, help needed.
