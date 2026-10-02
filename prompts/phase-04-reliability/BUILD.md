# BUILD — Phase 04 reliability (NORMAL, B2-1/3)

Type NORMAL (sequential after B1 ✅). No siblings running. OWN files: `src/reliability/*`, `src/verifier/*`, `tests/test_reliability*.py`. DO NOT TOUCH: `src/runtime/*` (01 frozen except via HELP), `src/tools/*`, `src/memory/*`, `src/policy/*`, `context/*`. Read-only: `src/contracts/verdict.py`, `src/ledger/*`, `src/runtime/loop.py`, `prompts/batch-B1-TEST-RESULT.md` findings F1–F4.

## Context + end goal
`prompts/00-plan.md` goal: invoice intake verified + evidence. B1 proved happy path offline. You make it hold up when things fail.

## Goal
Retries with backoff + replan on failed step + verifier predicates hardened + HITL approval CLI + checkpoint/resume + `plan_source` in evidence.

## Deliverables (OWN only)
- `src/reliability/retry.py` (exponential backoff, jitter, max 3, retryable vs fatal error classes), `replan.py` (one replan on failed step via planner, keeps succeeded cache), `checkpoint.py` (resume `--runs <dir> --resume <run_id>`).
- `src/verifier/checks.py` (emit `Predicate`/`Verdict` per contracts: non_empty_goal, plan_has_steps, every_step_resolved, no_silent_skips, each_success_has_evidence, audit_trail_complete + per-step criterion; fail-closed on missing evidence).
- `src/reliability/hitl.py` + CLI `python3 -m src.reliability.hitl --pending/--approve <request_id>` (reads `data/gate.jsonl` queue=pending, writes closed+approver).
- `tests/test_reliability_offline.py` (flaky tool succeeds on 3rd try; fatal 422 no retry; resume completes; HITL approve releases; empty task blocked).

## Criteria (must run)
- `python3 -m pytest tests/test_reliability_offline.py tests/test_runtime_smoke.py -q` green.
- `ERP_URL=http://127.0.0.1:8902 python3 -m src.runtime.loop --task "find latest invoice from Company X and post it to the ERP" --offline --tools auto --runs /tmp/b2-runs` → pass 8/8 cold, replay `cached/cached` warm.
- Stub-422 run → `failed` (not green), 1 retry, verdict fail, rc=1. `plan_source` present in `evidence.json:run`.
- B1 F3 carried: same (run,step,attempt) re-record returns data-failure, never unhandled `IntegrityError` out of `run_step`.

## Constraints (verified)
- WAL `journal_mode=WAL; synchronous=NORMAL; busy_timeout=5000`: https://www.sqlite.org/wal.html
- Tool strict schema unchanged: https://developers.openai.com/api/docs/guides/function-calling
- Quality ponytail: no new deps, deterministic (seeded jitter in tests), secrets redacted in checkpoint/HITL log. Fast: backoff only on retry path, happy path <2s. Secure: HITL required for `requires_approval` or amount>threshold; deny-by-default; audit every decision.

## Order
Write `prompts/phase-04-reliability/REPORT.md` with files changed, cmds+raw output, verify steps, limits, help needed.
