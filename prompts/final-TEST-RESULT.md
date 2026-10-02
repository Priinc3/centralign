# final-TEST-RESULT — ✅ VERIFIED (1 fix applied, 1 pre-submit action outstanding)

Run: 2026-10-02, macOS (darwin), Python 3.14, offline, `OPENAI_API_KEY` unset.
Verdict: **DONE-ready** — all 5 regression commands hold, all 6 acceptance items verified from evidence.
Outstanding before form submit: `<GITHUB_URL>` / `<VIDEO_URL>` placeholders in `SUBMISSION.md`.

## 1. Regression — all 5 commands, raw output

### 1.1 `python3 -m pytest tests/ -q`
```
........................................................................ [ 62%]
..........................................s.                             [100%]
115 passed, 1 skipped in 8.02s
```
Skip is the browser path only: `SKIPPED [1] tests/test_tools_smoke.py:212: playwright not
installed; allowlist tests above still run`. Nothing else is skipped.

### 1.2 `rm -rf /tmp/final && bash demo/run.sh /tmp/final` — rc=0
```
CentrAlign demo · scratch /tmp/final · offline, no API key needed
CentrAlign · AI operator for invoice intake · offline, no API key needed
seed        3 files in data/seed/invoices, newest = CX-2024-0912 $4,820.00 due 2024-10-12
fresh       /tmp/final/sim.db  (empty ERP db)
sim ERP     http://127.0.0.1:63696  db=/tmp/final/sim.db  (started for this run, stopped when it ends)
fresh       /tmp/final/runs  (run root)
fresh       /tmp/final/gate.jsonl  (approval queue)
erp rows    0
task        find latest invoice from Company X and post it to the ERP

run 1  51083e658072
  ✓ s1  invoice_find_latest    CX-2024-0912  $4,820.00 USD  due 2024-10-12
  ⏸ s2  erp_post_invoice       not posted — waiting for a human to approve it (queued below)

1 approval needed before this can continue:
  ✓ 06f9143b26ab  erp_post_invoice $4,820.00  approved by demo-operator   (erp_post_invoice requires approval)

run 2  continuing 51083e658072  (new run id: the ledger is append-only)
  ↻ s1  invoice_find_latest    CX-2024-0912  $4,820.00 USD  due 2024-10-12
  ✓ s2  erp_post_invoice       ERP row #1 created

verdict: pass 8/8   replayed=1   plan: heuristic   run: 937a0c263114
ERP count: 1
evidence: /tmp/final/runs/937a0c263114/evidence.json
next: bash demo/run.sh --append   # same scratch, same task: watch replayed=2
```

### 1.3 `bash demo/run.sh /tmp/final --append` — rc=0
```
CentrAlign demo · scratch /tmp/final · offline, no API key needed
CentrAlign · AI operator for invoice intake · offline, no API key needed
seed        3 files in data/seed/invoices, newest = CX-2024-0912 $4,820.00 due 2024-10-12
kept        /tmp/final/sim.db  (kept, as asked)
sim ERP     http://127.0.0.1:63710  db=/tmp/final/sim.db  (started for this run, stopped when it ends)
kept        /tmp/final/runs  (kept, as asked)
kept        /tmp/final/gate.jsonl  (kept, as asked)
erp rows    1
task        find latest invoice from Company X and post it to the ERP

run 1  9430c4326be4
  ↻ s1  invoice_find_latest    CX-2024-0912  $4,820.00 USD  due 2024-10-12
  ↻ s2  erp_post_invoice       ERP row #1 created

verdict: pass 8/8   replayed=2   plan: heuristic   run: 9430c4326be4
ERP count: 1  (unchanged: nothing was double-posted)
evidence: /tmp/final/runs/9430c4326be4/evidence.json
next: python3 -m src.cli.main demo   # again without --append: a cold run
```

### 1.4 `python3 -m src.security.scan` — rc=0
```
scanning 6 trees for credentials  … none
allowlisted canaries  2  (tests/, marker-checked: the line must still say why)
guards  deny unknown tool · deny evil host + suffix trick · deny /etc traversal · redactor masks a live secret

findings: 0  → safe to publish
```

### 1.5 `python3 -m src.cli.main run --task "" ; echo rc=$?` — **rc=1**
```
CentrAlign · AI operator for invoice intake · offline, no API key needed
runs        /tmp/centralign-demo/runs  (empty ask: nothing to audit, so not under the repo's runs/)
task        (empty)

run 1  6200ad6a205b

verdict: blocked / No task given   replayed=0   plan: heuristic   run: 6200ad6a205b
  ✗ non_empty_goal: No task given
  ✗ plan_has_steps: the plan contains at least one dispatchable step
evidence: /tmp/centralign-demo/runs/6200ad6a205b/evidence.json
next: python3 -m src.cli.main demo   # the whole thing, one command, offline
```

## 2. Goal acceptance

- [x] **Natural task → completed work (not explanation).** Cold demo above: `bash demo/run.sh /tmp/final`,
  rc=0, `verdict: pass 8/8`, `run.status=completed`, ERP count 1. Natural ask, no flags, no key.
- [x] **Plan→Execute→Observe→Adapt→Verify→Complete in evidence (8/8 predicates).**
  `evidence.json#/events` carries the stages as ledger events (`run.stage` payloads: `resume`,
  `execute`, `observe`, `replan`; plus `step.planned` = plan, `verify.checked`, `run.completed`).
  Predicates are the 6 contracted gates + 2 per-step criteria (`criterion:s1`, `criterion:s2`), all `passed: true`.
- [x] **Failure recovery: downed-ERP rc=1 → resume pass, no double post.** Exercised live against a
  dead port, then the same scratch after bringing the ERP up (commands + output below).
- [x] **Human approval: unapproved post blocked with next action; approved posts once.** Exercised live
  non-interactively (below): blocked rc=1 with copy-pasteable next commands, ERP count unchanged; after
  `hitl --approve`, rc=0 and the row count stays 1.
- [x] **Verification + evidence.** `evidence.json` keys: `bundle_version, run, plan, steps, events, tools,
  totals, verdict, limits, written_at`. `verdict.summary = "8/8 predicates passed"`. `replayed=N` on the
  CLI equals `totals.cached` in the bundle (cold `replayed=1` / `cached: 1`, `--append` `replayed=2` /
  `cached: 2`) and matches `tools_actually_executed` vs `tools_replayed` — honest, not cosmetic.
- [~] **Submission pack.** README.md ✅, SUBMISSION.md ✅, requirements.txt ✅ (4 pinned deps + optional
  playwright, demo needs none), .gitignore ✅ (runs/, *.db, *.jsonl, .env, __pycache__), demo/video-script.md ✅.
  **`<GITHUB_URL>` and `<VIDEO_URL>` in SUBMISSION.md lines 7–8, 63, 68 are still placeholders** — fill before submit.

### 2.1 Failure-recovery drill (rc=1 → resume → pass, ERP count 1)
```bash
export ERP_URL=http://127.0.0.1:63199          # nothing listening: the ERP is down
python3 -m src.cli.main run --task "find latest invoice from Company X and post it to the ERP" \
  --runs /tmp/rec/runs --queue /tmp/rec/gate.jsonl --approve ops-lead
```
```
run 2  continuing 6485a1c55db7  (new run id: the ledger is append-only)
  ↻ s1  invoice_find_latest    CX-2024-0912  $4,820.00 USD  due 2024-10-12
  ✗ s2  erp_post_invoice       ERP unreachable at http://127.0.0.1:63199/invoices: <urlopen error [Errno 61] Connection refused>
  ✗ s2  erp_post_invoice       ERP unreachable at http://127.0.0.1:63199/invoices: <urlopen error [Errno 61] Connection refused>
  ✗ s2  erp_post_invoice       ERP unreachable at http://127.0.0.1:63199/invoices: <urlopen error [Errno 61] Connection refused>
  ↻ s1  invoice_find_latest    CX-2024-0912  $4,820.00 USD  due 2024-10-12
  ✗ s2  erp_post_invoice       ERP unreachable at http://127.0.0.1:63199/invoices: <urlopen error [Errno 61] Connection refused>
  ✗ s2  erp_post_invoice       ERP unreachable at http://127.0.0.1:63199/invoices: <urlopen error [Errno 61] Connection refused>
  ✗ s2  erp_post_invoice       ERP unreachable at http://127.0.0.1:63199/invoices: <urlopen error [Errno 61] Connection refused>

verdict: fail 6/8   replayed=1   plan: replan:heuristic   run: bd760d7dfd6a
  ✗ every_step_resolved: s2:ERP unreachable at http://127.0.0.1:63199/invoices: <urlopen error [Errno 61] Connection refused>
downed-ERP rc=1
```
Adapt is visible: `plan: replan:heuristic` and `run.stage {"stage": "replan", "reused": ["s1"]}` in the bundle.

```bash
python3 sim_app/server.py --port 63199 --db /tmp/rec/sim.db &
ERP_URL=http://127.0.0.1:63199 python3 -m src.cli.main run --task "…" --runs /tmp/rec/runs --queue /tmp/rec/gate.jsonl --approve ops-lead
```
```
run 1  fbeefaad5394
  ↻ s1  invoice_find_latest    CX-2024-0912  $4,820.00 USD  due 2024-10-12
  ✓ s2  erp_post_invoice       ERP row #1 created

verdict: pass 8/8   replayed=1   plan: heuristic   run: fbeefaad5394
resume rc=0
--- ERP rows ---
{"count": 1, "invoices": [{"id": 1, "idempotency_key": "inv-8e41e8ea926c4efb4a4836cb", "vendor": "ACME SUPPLY CO.", "company": "Company X", "invoice_number": "CX-2024-0912", "amount": "4820.00", "currency": "USD", "due_date": "2024-10-12", "source_file": "INV-X-2024-0912-acme.pdf", …}]}
```

### 2.2 Human-approval drill (unapproved → blocked + next action; approved → posts once)
```bash
ERP_URL=http://127.0.0.1:63199 python3 -m src.cli.main run --task "find latest invoice from Company X and post it to the ERP" \
  --runs /tmp/rec2/runs --queue /tmp/rec2/gate.jsonl < /dev/null
```
```
1 approval needed before this can continue:
  ⏸ 1e1c4bea0833  erp_post_invoice $4,820.00  waiting for a human   (erp_post_invoice requires approval)
      next: python3 -m src.reliability.hitl --approve 1e1c4bea0833 --approver <you>
      then: python3 -m src.cli.main run --task "find latest invoice from Company X and post it to the ERP" --runs /tmp/rec2/runs --approve <you>

verdict: blocked / 7/8 predicates passed   replayed=0   plan: heuristic   run: 0b4dc96fd4c7
unapproved rc=1
--- ERP rows (unchanged?) ---
count = 1
```
```bash
python3 -m src.reliability.hitl --queue /tmp/rec2/gate.jsonl --approve 1e1c4bea0833 --approver ops-lead
→ 1e1c4bea0833 granted by ops-lead
ERP_URL=http://127.0.0.1:63199 python3 -m src.cli.main run --task "…" --runs /tmp/rec2/runs --queue /tmp/rec2/gate.jsonl < /dev/null
```
```
run 1  60271d53532f
  ↻ s1  invoice_find_latest    CX-2024-0912  $4,820.00 USD  due 2024-10-12
  ✓ s2  erp_post_invoice       ERP row #1 already posted (idempotent)

verdict: pass 8/8   replayed=1   plan: heuristic   run: 60271d53532f
approved rc=0
count = 1 ['inv-8e41e8ea926c4efb4a4836cb']
```
Worth noting for the video: `/tmp/rec2` was a *different* run tree against the *same* ERP, and the post
came back `already posted (idempotent)` — the idempotency key, not the run id, is what stops double posting.

## 3. Fix applied during this gate

`src/runtime/loop.py:323` wrote `"no approval channel in Phase 01 (policy gate is Phase 03)"` into every
`evidence.json#/limits`. Phase 03/05 shipped the gate, so the bundle contradicted the run that produced it
(flagged in `prompts/phase-05-demo-ux/REPORT.md:273` and left unfixed). Replaced with the true limit:
`"one operator: read-only tools run unattended, side-effecting tools need a human approval on the queue"`.
Also `requirements.txt:1` said "the 94 tests" → now "115 tests (116 collected, 1 needs playwright)".
Re-ran §1 after both edits: unchanged results (115 passed / cold rc=0 / append rc=0 / scan rc=0 / empty rc=1),
and all three fresh bundles now carry the corrected `limits`.

## 4. Known limits restated (not re-litigated, re-verified as still true)

- **Company Y `.txt` planner glob** — confirmed live: the planner hardcodes `pattern: "*.pdf"`
  (`src/runtime/planner.py:230`), so a Company Y task fails closed (`✗ s1 … no parseable invoice for
  Company Y`, `verdict: fail 5/8`, rc=1). The tool itself parses `INV-Y-2024-0805-other.txt` fine when
  called without the glob. Wrong-but-red, never a false green.
- **LLM path unexercised** — `OPENAI_API_KEY` unset in every run above, so `plan: heuristic` /
  `replan:heuristic` throughout. The `--llm` flag and `openai==2.24.0` are shipped but unproven against a live key.
- **Single-operator scope** — one approval queue (`--queue`), one approver identity, no per-team policy scoping.
- **Video URL placeholder** — `<VIDEO_URL>` / `<GITHUB_URL>` must be filled before the form submit (§2, last item).

Environment note: this directory is **not a git repo** (no `.git`). `.gitignore` is present and correct, but
`git init` + a commit are still needed before a GitHub URL exists.