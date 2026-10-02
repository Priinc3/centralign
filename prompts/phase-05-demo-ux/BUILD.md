# BUILD — Phase 05 demo-ux (NORMAL, B2-2/3)

Type NORMAL (after 04 ✅). No siblings. OWN files: `src/cli/*`, `demo/*`, `tests/test_demo*.py` (+ `src/ui/*` only if tiny static page, else skip — ponytail). DO NOT TOUCH: `src/runtime/*`, `src/ledger/*`, `src/tools/*`, `src/memory/*`, `src/policy/*`, `src/reliability/*`, `src/verifier/*`, `context/*`. Read-only: `src/reliability/hitl.py`, `src/ledger/evidence.py`, B1/B2 TEST-RESULTs.

## Context + end goal
`prompts/00-plan.md` goal: offline invoice demo <60s setup, evidence + approvals. B1+B2 proved engine. You make it beautiful, fast, obvious.

## Goal
One-command demo an evaluator runs blind: seeded invoice → verified post → evidence shown, approvals surfaced, replay transparent.

## Deliverables (OWN only)
- `src/cli/main.py` (`python3 -m src.cli.main demo|run --task ... --approve/--runs`: <1s first feedback line, prints `replayed=N` next to verdict (B1-F1), progress per step, plain-word errors, destructive=confirm+undo note).
- `src/cli/doctor.py` (`... doctor`: python version, deps present/absent, sim reachability, suggest `pip install playwright` only if browser wanted).
- `demo/run.sh` (fresh scratch sim `--db /tmp/...` + fresh `--runs` dir — kills B1-F2 dirty-DB flake; end-to-end <60s) + `demo/script.md` (30s narration for video).
- `tests/test_demo_offline.py` (cold demo passes 8/8; warm shows `replayed=2`; empty→blocked wording; doctor rc=0 offline).
- Wire `authorizer=hitl.authorizer` from CLI (01 FIX-2 HELP-5 enabled; do NOT re-edit loop).

## Criteria (must run)
- `rm -rf /tmp/d5 && bash demo/run.sh` → `verdict: pass 8/8`, `ERP count: 1`, `replayed` line shown, wall <60s (target <15s without playwright install).
- `python3 -m src.cli.main run --task ""` → `blocked / No task given` rc=1.
- `python3 -m pytest tests/test_demo_offline.py -q` green; full `python3 -m pytest tests/ -q` stays green.
- No network needed except localhost sim; offline + no-key path prints `plan: heuristic`.

## Constraints (verified)
- Playwright optional: https://playwright.dev/python/docs/intro (only for browser path; demo defaults to files+ERP).
- Strict tool-calling unchanged: https://developers.openai.com/api/docs/guides/function-calling
- Quality: quality>quantity — one beautiful CLI > CLI+web; stdlib-first; secrets redacted in all output. Fast: first line <1s, no sleeps on happy path. UX: obvious next action, feedback <1s, no dead ends, plain words.

## Order
Write `prompts/phase-05-demo-ux/REPORT.md` with files changed, cmds+raw output, verify steps, limits, help needed.
