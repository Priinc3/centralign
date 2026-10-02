# VERIFY — Phase 05 demo-ux — ✅ VERIFIED

Criteria 1–4 PASS proven by raw output: cold `demo/run.sh` 0.45s `pass 8/8 replayed=1 ERP count 1`; warm `--append replayed=2` count unchanged; empty→`blocked / No task given` rc=1; 6 demo tests + full 89 passed/1 skipped; first line 54ms, `plan: heuristic`, doctor ready offline.

## Findings (0 🔴/🟠)
- OWN scope held (runtime/ledger/tools/memory/policy/reliability/verifier/context untouched — verified claim). No `src/ui/*` — accepted ponytail (evidence bundle is second view).
- HITL genuinely wired (`hitl.authorizer` partial, pty prompt + non-interactive `blocked 7/8 ERP 0 rows` + `--approve` path). B1-F1/F2 closed: `replayed=N` on verdict line; scratch wipe incl. queue.
- 🟡 ceilings waived: 40ms poll follower; replayed counts final run only; 1 approval round-trip; `--approve` unattended; doctor doesn't check registry load; subprocess sim; scratch confined to /tmp. Two frozen-file notes (executor wording, planner base_url) → optional, carried to 06 if touched, else docs.

## Goal check
Evaluator can run blind <60s. Open Phase 06.

## FIX-1 ✅ VERIFIED
F3 empty→scratch (repo `runs/` unchanged, explicit `--runs` wins) + F4 queue help + F5 doctor note proven; 7 demo tests, 115 suite green; demo pass 8/8. OWN held (cli/tests only).
