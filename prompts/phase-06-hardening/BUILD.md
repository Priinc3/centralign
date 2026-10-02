# BUILD — Phase 06 hardening + submission (NORMAL, B2-3/3)

Type NORMAL (after 05 ✅). No siblings. OWN files: `src/security/*`, `README.md`, `SUBMISSION.md`, `tests/test_security*.py` (+ `requirements.txt`, `.gitignore`, `demo/video-script.md` if missing). DO NOT TOUCH: `src/runtime/*`, `src/ledger/*`, `src/tools/*`, `src/memory/*`, `src/policy/*`, `src/reliability/*`, `src/verifier/*`, `src/cli/*`, `context/*`. Read-only: all REPORTs, B1-TEST-RESULT, demo/run.sh output.

## Context + end goal
Deadline Oct 4 5:30 PM IST, Google Form + GitHub link + README + demo video. Engine+demo proven (89 tests). You make it submittable and secure.

## Goal
Security pass + submission pack an evaluator accepts without asking for setup help.

## Deliverables (OWN only)
- `src/security/scan.py` (secret grep: `sk-`, bearer, password/token in code+context+runs; allowlist/traversal self-tests; `.env` never committed check) + `tests/test_security_hardening.py` (evil.com blocked incl. suffix, `../../etc/passwd` envelope no leak, redactor positive control, no secrets in tree, gate deny unknown).
- `requirements.txt` pinned (openai, playwright optional note, pydantic, pyyaml, pytest) + `.gitignore` (runs/, *.db, *.jsonl, __pycache__, .env).
- `README.md` (30s pitch, `bash demo/run.sh` quickstart <60s, arch diagram Goal→…→Complete, decisions, models/APIs, assumptions, limits, what-next).
- `SUBMISSION.md` (eval criteria mapped: autonomy/execution/reliability/verification/generalization/quality/product/understanding + narrow-genuine statement + video link placeholder).
- `demo/video-script.md` (60–90s beats matching demo/run.sh output).

## Criteria (must run)
- `python3 -m pytest tests/ -q` stays green (≥89 passed).
- `rm -rf /tmp/d6 && bash demo/run.sh /tmp/d6` → pass 8/8, count 1, <60s.
- `python3 -m src.security.scan` → 0 findings (only redactor's own regex/docstring allowed, must allowlist).
- Repo clean for publish: `git status --short` shows no `runs/`, `*.db`, `*.jsonl`, `.env`; `grep -r sk- src/ context/ sim_app/` only redactor.

## Constraints (verified)
- WAL: https://www.sqlite.org/wal.html ; strict tools: https://developers.openai.com/api/docs/guides/function-calling ; Playwright optional: https://playwright.dev/python/docs/intro
- Secure defaults: deny-by-default, sandbox `data/`, allowlist, redact before write/log, no creds in repo. Fast: scan <5s. Quality: honest limits, no mocked autonomy claims.

## Order
Write `prompts/phase-06-hardening/REPORT.md` with files changed, cmds+raw output, verify steps, limits, video link or placeholder + how to record.
