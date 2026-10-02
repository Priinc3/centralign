# FIX-2 — Phase 05 demo-ux (F3: Gemini key never reaches `run`)

Scope locked: `src/cli/main.py` (1 line) + `tests/test_demo_offline.py` (1 test). Nothing else.

## Problem
`cmd_run` computes `offline = args.offline or not os.environ.get("OPENAI_API_KEY")`, so a Gemini-only owner always plans heuristically via `run`; only `demo --llm` reaches the 07 router.

## Fix
`offline = args.offline or not (os.environ.get("OPENAI_API_KEY") or os.environ.get("GEMINI_API_KEY"))`
Test: with `GEMINI_API_KEY=fake` (+ stubbed transport or `--llm` flag path) `run` attempts the router (offline False in state/evidence); without any key behavior unchanged (heuristic, offline True).

## Verify-with
- `python3 -m pytest tests/test_demo_offline.py tests/test_llm_router_keys.py -q` green + full suite green.
- `GEMINI_API_KEY=x python3 -m src.cli.main run --task "demo" --runs /tmp/fx2 --queue /tmp/fx2q` shows LLM attempt (not silent heuristic); no-key run unchanged.
- Append FIX-2 section to `prompts/phase-05-demo-ux/REPORT.md`.
