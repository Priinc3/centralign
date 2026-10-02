# Batch B2 TEST RESULT — 04+05+06 integration (reliability × demo × security)

Ran 2026-10-02. Verdict: **PASS — every product behavior the batch names held; 5 findings, all
minor, none blocking.** One finding (F1) is a bug in the batch's own command, not in the product:
Phase 4's "latest evidence" one-liner reports `blocked` for a demo that passed.

| phase | check | result |
|---|---|---|
| 00 | full suite + cold demo | **PASS** — 114 passed, 1 skipped; demo pass 8/8 |
| 01 | happy / replay / resume | **PASS** — replayed=0 → 2, ERP count stays 1 |
| 02 | E1 empty task, E2 downed ERP, E3 double approval | **PASS** — rc=1, retry events, resume→pass, refused rc=2 |
| 03 | security scan + hardening + publish tree | **PASS** — 0 findings, 25 tests, 80 files clean |
| 04 | cross-phase evidence read | **PASS** (via corrected command; F1) |

## Env note

| item | value |
|---|---|
| python | 3.14.3 |
| pytest | 9.1.1 — full suite in 7.11s |
| playwright | absent (`doctor` reports `note`, not a blocker — demo path is files + ERP) |
| scratch | `/tmp/b2t` (cold demo), `/tmp/b2t-down` (E2), ERP db `/tmp/b2t-down/sim.db` |
| sim ERP | demo picks a free port per run (`:62729` cold, `:62739` append); E2 used 8901 |
| cleanup | sim on 8901 stopped, `/tmp/gi2` removed, port 8901 free at end of run |

The demo chooses its own ERP port rather than 8901 (`src/cli/main.py:87`, "A hard-coded 8901
collides with a sim the user already runs"). E2 needed a stopped ERP to fail against, so it used
`run` (which takes `$ERP_URL`, default 8901) rather than `demo`.

---

## 0. Setup — PASS

```
$ python3 -m pytest tests/ -q
........................................................................ [ 62%]
.........................................s.                              [100%]
114 passed, 1 skipped in 7.11s
```

```
$ rm -rf /tmp/b2t && bash demo/run.sh /tmp/b2t
CentrAlign demo · scratch /tmp/b2t · offline, no API key needed
CentrAlign · AI operator for invoice intake · offline, no API key needed
seed        3 files in data/seed/invoices, newest = CX-2024-0912 $4,820.00 due 2024-10-12
fresh       /tmp/b2t/sim.db  (empty ERP db)
sim ERP     http://127.0.0.1:62729  db=/tmp/b2t/sim.db  (started for this run, stopped when it ends)
fresh       /tmp/b2t/runs  (run root)
fresh       /tmp/b2t/gate.jsonl  (approval queue)
erp rows    0
task        find latest invoice from Company X and post it to the ERP

run 1  e69d6022bba1
  ✓ s1  invoice_find_latest    CX-2024-0912  $4,820.00 USD  due 2024-10-12
  ⏸ s2  erp_post_invoice       not posted — waiting for a human to approve it (queued below)

1 approval needed before this can continue:
  ✓ 5854bb3d85eb  erp_post_invoice $4,820.00  approved by demo-operator   (erp_post_invoice requires approval)

run 2  continuing e69d6022bba1  (new run id: the ledger is append-only)
  ↻ s1  invoice_find_latest    CX-2024-0912  $4,820.00 USD  due 2024-10-12
  ✓ s2  erp_post_invoice       ERP row #1 created

verdict: pass 8/8   replayed=1   plan: heuristic   run: ddd7c2e1af65
ERP count: 1
evidence: /tmp/b2t/runs/ddd7c2e1af65/evidence.json
next: bash demo/run.sh --append   # same scratch, same task: watch replayed=2
```

Worth naming: the approval gate splits one logical task into two run_ids and the ledger keeps both.
The demo narrates it instead of hiding it.

## 1. Happy + replay + resume — PASS

### 1a. Replay against a warm scratch

```
$ bash demo/run.sh /tmp/b2t --append
CentrAlign demo · scratch /tmp/b2t · offline, no API key needed
CentrAlign · AI operator for invoice intake · offline, no API key needed
seed        3 files in data/seed/invoices, newest = CX-2024-0912 $4,820.00 due 2024-10-12
kept        /tmp/b2t/sim.db  (kept, as asked)
sim ERP     http://127.0.0.1:62739  db=/tmp/b2t/sim.db  (started for this run, stopped when it ends)
kept        /tmp/b2t/runs  (kept, as asked)
kept        /tmp/b2t/gate.jsonl  (kept, as asked)
erp rows    1
task        find latest invoice from Company X and post it to the ERP

run 1  10767e0fc170
  ↻ s1  invoice_find_latest    CX-2024-0912  $4,820.00 USD  due 2024-10-12
  ↻ s2  erp_post_invoice       ERP row #1 created

verdict: pass 8/8   replayed=2   plan: heuristic   run: 10767e0fc170
ERP count: 1  (unchanged: nothing was double-posted)
evidence: /tmp/b2t/runs/10767e0fc170/evidence.json
next: python3 -m src.cli.main demo   # again without --append: a cold run
```

The documented `replayed=0 → replayed=2` progression is real, and the second run executes **zero**
tools (Phase 4 totals confirm: `tools_actually_executed: []`). B1's warm-ledger complaint does not
reproduce here — `--append` states what it kept and why.

### 1b. Doctor

```
$ python3 -m src.cli.main doctor
CentrAlign · AI operator for invoice intake · offline, no API key needed

CentrAlign doctor
python      ok     3.14.3 (need >= 3.11)
pydantic    ok     2.13.4 — frozen contracts (ToolManifest, Verdict)
yaml        ok     6.0.3 — context/company.yaml + policies.yaml
openai      ok     2.24.0 — LLM planner (the demo plans heuristically without it)
pytest      ok     9.1.1 — running the test suite
playwright  note   absent — only the browser path needs it; the demo uses files + ERP
context     ok     company.yaml + policies.yaml + tools.yaml valid
policy      ok     auto-post <= $1,000.00 unattended; above that a human approves; approval queue = data/gate.jsonl
seed        ok     3 invoices in data/seed/invoices
runs dir    ok     /Users/princegondaliya/Learning/Projects/temp/Draft/centralign/runs is writable
sim ERP     note   not running at http://127.0.0.1:8901 — the demo starts its own; or: python3 sim_app/server.py --port 8901 --db /tmp/sim.db
network     ok     not needed: no API key, no internet — only 127.0.0.1 is contacted

ready: the offline demo runs (python3 -m src.cli.main demo)
rc=0
```

### 1c. Checkpoint CLI reachable

```
$ ERP_URL=http://127.0.0.1:8902 python3 -m src.reliability.checkpoint --help
usage: python -m src.reliability.checkpoint [-h] [--runs RUNS]
                                            [--resume RUN_ID] [--json]

Checkpoint + resume. The ledger is the durable state; a checkpoint only
records how far this process got, so a resume can say out loud what it
rc=0
```

## 2. Edges — PASS

### E1. Empty task — blocked, rc=1

```
$ python3 -m src.cli.main run --task ""
CentrAlign · AI operator for invoice intake · offline, no API key needed
task        (empty)

run 1  3641cf0ff33f

verdict: blocked / No task given   replayed=0   plan: heuristic   run: 3641cf0ff33f
  ✗ non_empty_goal: No task given
  ✗ plan_has_steps: the plan contains at least one dispatchable step
evidence: runs/3641cf0ff33f/evidence.json
next: python3 -m src.cli.main demo   # the whole thing, one command, offline
rc=1
```

Failing on `non_empty_goal` *and* `plan_has_steps` is right — an empty ask has no plan either, and
both predicates are reported rather than the first one short-circuiting. See F3 about where the
evidence landed.

### E2. ERP down → fail rc=1 with retries → resume → pass, ERP count 1

```
$ python3 -m src.cli.main run --task "find latest invoice from Company X and post it to the ERP" \
    --runs /tmp/b2t-down --approve demo-operator
run 1  9a7ea53163ad
  ✓ s1  invoice_find_latest    CX-2024-0912  $4,820.00 USD  due 2024-10-12
  ⏸ s2  erp_post_invoice       not posted — waiting for a human to approve it (queued below)

1 approval needed before this can continue:
  ✓ 06480f6610f9  erp_post_invoice $4,820.00  approved by demo-operator   (erp_post_invoice requires approval)

run 2  continuing 9a7ea53163ad  (new run id: the ledger is append-only)
  ↻ s1  invoice_find_latest    CX-2024-0912  $4,820.00 USD  due 2024-10-12
  ✗ s2  erp_post_invoice       ERP unreachable at http://127.0.0.1:8901/invoices: <urlopen error [Errno 61] Connection refused>
  ✗ s2  erp_post_invoice       ERP unreachable at http://127.0.0.1:8901/invoices: <urlopen error [Errno 61] Connection refused>
  ✗ s2  erp_post_invoice       ERP unreachable at http://127.0.0.1:8901/invoices: <urlopen error [Errno 61] Connection refused>
  ↻ s1  invoice_find_latest    CX-2024-0912  $4,820.00 USD  due 2024-10-12
  ✗ s2  erp_post_invoice       ERP unreachable at http://127.0.0.1:8901/invoices: <urlopen error [Errno 61] Connection refused>
  ✗ s2  erp_post_invoice       ERP unreachable at http://127.0.0.1:8901/invoices: <urlopen error [Errno 61] Connection refused>
  ✗ s2  erp_post_invoice       ERP unreachable at http://127.0.0.1:8901/invoices: <urlopen error [Errno 61] Connection refused>

verdict: fail 6/8   replayed=1   plan: replan:heuristic   run: 6e2a776bcaa6
  ✗ every_step_resolved: s2:ERP unreachable at http://127.0.0.1:8901/invoices: <urlopen error [Errno 61] Connection refused>
evidence: /tmp/b2t-down/6e2a776bcaa6/evidence.json
next: python3 -m src.cli.main run --task "..." --runs /tmp/b2t-down   # replays, never re-posts
rc=1   (verified on a second invocation, which printed the same fail verdict)
```

Three attempts, then a replan, then three more — the retry ladder is real and the failure is
classified, not merely counted:

```
$ grep -n '"stage": "retry"' /tmp/b2t-down/6e2a776bcaa6/events.jsonl | head -1
{"actor": "executor", "payload": {"attempt": 1, "classify": "retryable", "delay_s": 0.401,
  "next_attempt": 2, "reason": "ERP unreachable at ...: <urlopen error [Errno 61] Connection refused>",
  "stage": "retry"}, "run_id": "6e2a776bcaa6", "seq": 7, "step_id": "s2", "tool": "erp_post_invoice", ...}
```

Sim back up on 8901, then resume the failed run by id:

```
$ python3 sim_app/server.py --port 8901 --db /tmp/b2t-down/sim.db &
$ curl -s http://127.0.0.1:8901/invoices            →  count before: 0

$ python3 -m src.reliability.checkpoint --runs /tmp/b2t-down --resume 7c5b4e16fb57
resumed 7c5b4e16fb57 -> run 26bef5abc691 [completed] verdict=pass
inherited: {'s1': 'cached', 's2': 'failed'}
steps:     ['cached', 'succeeded']
evidence:  /tmp/b2t-down/26bef5abc691/evidence.json
rc=0

$ curl -s http://127.0.0.1:8901/invoices
count after: 1
  row: 1 CX-2024-0912 4820.00
```

The resume says out loud what it inherited (`s1: cached`, `s2: failed`) and posts exactly once.
This is the phase-04 claim ("the ledger is the durable state") surviving a real outage.

### E3. Double approval refused — rc=2

```
$ python3 -m src.reliability.hitl --pending --queue /tmp/b2t/gate.jsonl
no pending approvals

$ python3 -m src.reliability.hitl --approve 5854bb3d85eb --approver demo-operator --queue /tmp/b2t/gate.jsonl
refused: request 5854bb3d85eb is already 'closed'
rc=2

$ python3 -m src.reliability.hitl --approve deadbeefdead --approver x --queue /tmp/b2t/gate.jsonl
refused: unknown request_id 'deadbeefdead'
rc=2
```

Both halves of deny-by-default hold: a closed request and an unknown id are refused, not
silently accepted. The queue tail shows why — decisions are appended, so closure is the last
record's `queue` field, not a mutable flag:

```
$ tail -2 /tmp/b2t/gate.jsonl
{"ts": "...", "tool": "erp_post_invoice", "verdict": "approve",  "reason": "erp_post_invoice requires approval", "risk": "write", "amount": 4820.0, "domain": null, "request_id": "5854bb3d85eb", "queue": "pending"}
{"ts": "...", "tool": "erp_post_invoice", "verdict": "granted",  "reason": "erp_post_invoice requires approval", "risk": "write", "amount": 4820.0, "domain": null, "request_id": "5854bb3d85eb", "queue": "closed", "approver": "demo-operator"}
```

## 3. Security + publish — PASS

```
$ python3 -m src.security.scan
scanning 6 trees for credentials  … none
allowlisted canaries  2  (tests/, marker-checked: the line must still say why)
guards  deny unknown tool · deny evil host + suffix trick · deny /etc traversal · redactor masks a live secret

findings: 0  → safe to publish
rc=0

$ python3 -m pytest tests/test_security_hardening.py -q
.........................                                                [100%]
25 passed in 0.14s
```

Publish surface — every file a `git add` would stage, checked for run artifacts:

```
$ rm -rf /tmp/gi2; git init -q /tmp/gi2
$ GIT_DIR=/tmp/gi2/.git GIT_WORK_TREE=. git add -An | wc -l
80
$ GIT_DIR=/tmp/gi2/.git GIT_WORK_TREE=. git add -An | grep -E "runs/|\.db$|\.jsonl$|\.env" || echo "publish-clean"
publish-clean
$ GIT_DIR=/tmp/gi2/.git GIT_WORK_TREE=. git add -An | grep -cE "jsonl|\.db|\.env"
0
```

The listing is real (80 files, starting `.gitignore`, `README.md`, `SUBMISSION.md`,
`context/company.yaml`) and carries no ledger, db, jsonl or `.env`. `.gitignore` covers `runs/`,
`*.db`, `*.jsonl`, `data/gate.jsonl`, `.env*`, `*.pem`, `__pycache__/`.

The prompt's `sk-` grep is not a leak check worth having (F2): every hit is the scanner describing
itself.

```
$ grep -rn "sk-" src/ context/ sim_app/ demo/ | grep -v events.py
Binary file src/security/__pycache__/scan.cpython-314.pyc matches
src/security/scan.py:31:    # sk- followed by real key entropy: the redactor's own literal (sk-[A-Za-z...]) cannot match.
src/security/scan.py:32:    "openai_key": re.compile(r"\bsk-[A-Za-z0-9_-]{20,}"),
src/security/scan.py:154:    probe = {"api_key": "sk-" + "A" * 24, "Authorization": "Bearer " + "b" * 20}
src/security/scan.py:155:    if redact(probe) == probe or "sk-" in json.dumps(redact(probe)):
Binary file src/contracts/__pycache__/events.cpython-314.pyc matches
Binary file src/policy/__pycache__/gate.cpython-314.pyc matches
src/policy/gate.py:1:"""Risk-tiered approval gate: allow | approve | deny. Deterministic, no LLM.
```

Line 32 is the detection regex; line 154 builds its probe by concatenation so the file never holds
key-shaped text; `gate.py:1` is the substring `approve`. No secret material.

## 4. Cross-phase (04 × 05 × 06) — PASS via the corrected command

As written, the batch command picks the wrong run (F1). Sorting run ids lexicographically is not
recency: `sorted(glob(...))[-1]` returned `e69d6022bba1`, which is the *oldest* run of the three.

```
$ python3 -c "... sorted(glob.glob('/tmp/b2t/runs/*/evidence.json'))[-1] ..."
blocked 7/8 predicates passed
plan_source: heuristic
totals: {'cached': 0, 'events': 10, 'failed': 0, 'skipped': 1, 'steps': 2, 'succeeded': 1,
         'tools_actually_executed': ['invoice_find_latest'], 'tools_replayed': []}
```

The ledger knows the order, so ask it:

```
$ python3 -c "
import sqlite3
c=sqlite3.connect('/tmp/b2t/runs/_ledger.sqlite3')
for r in c.execute('SELECT run_id, status, created_at FROM runs ORDER BY created_at'): print(r)"
('e69d6022bba1', 'blocked',   '2026-10-02T09:08:43.823Z')
('ddd7c2e1af65', 'completed', '2026-10-02T09:08:43.841Z')
('10767e0fc170', 'completed', '2026-10-02T09:08:46.847Z')

$ python3 -c "import json; e=json.load(open('/tmp/b2t/runs/10767e0fc170/evidence.json')); \
  print(e['verdict']['status'], e['verdict']['summary']); \
  print('plan_source:', e['run'].get('plan_source')); print('totals:', e.get('totals'))"
pass 8/8 predicates passed
plan_source: heuristic
totals: {'cached': 2, 'events': 8, 'failed': 0, 'skipped': 0, 'steps': 2, 'succeeded': 0,
         'tools_actually_executed': [], 'tools_replayed': ['erp_post_invoice', 'invoice_find_latest']}
```

This is the integration claim in one line: the newest run passes 8/8, plans heuristically
(no API key), and executed **no tools** — both steps replayed from the ledger, so the demo's second
pass writes zero rows and still returns a complete verdict. Note `mtime` is *not* a safe substitute:
all three evidence files share the same wall-clock second.

---

## Findings

| # | sev | where | finding |
|---|---|---|---|
| F1 | med | `prompts/batch-B2-TEST.md:33` | The "latest evidence" one-liner orders run dirs by name, not time, so Phase 4 reports `blocked 7/8` for a run that passed. Fix: `SELECT ... ORDER BY created_at` on `runs/_ledger.sqlite3` (mtime ties within one second). |
| F2 | low | `prompts/batch-B2-TEST.md:27` | `grep -rn "sk-"` matches the scanner's own regex, its concatenation-built probe, `__pycache__` binaries, and `gate.py:1` ("approve"). It cannot distinguish a leak from a description of one. Use `python3 -m src.security.scan` alone, or add `--include=*.py -I` and exclude `src/security/scan.py`. |
| F3 | low | `src/cli/main.py` | `run --task ""` writes `runs/3641cf0ff33f/` into the repo working tree. It is gitignored so nothing publishes, but a rejected-input probe still leaves a run dir. `demo/run.sh` sends `--runs` to scratch; `run` does not. |
| F4 | low | `src/cli/main.py:548` | `--queue` help says `default: context/company.yaml`; the real default is the value of `context/company.yaml:approval.queue` = `data/gate.jsonl` (confirmed: E2's approval landed in `data/gate.jsonl` with no `--queue` flag). Copy the file name and it reads like a path that holds the queue. |
| F5 | info | `src/cli/doctor.py:130` | `doctor` probes `$ERP_URL`/8901 while `demo` binds a free port per run, so a clean run still prints `sim ERP note not running`. Accurate, but the line invites a reviewer to wonder why the demo just worked. |

Not findings, checked and fine: E1's second failing predicate; the two-run_ids-per-gated-task
shape (narrated, ledger keeps both); `doctor`'s playwright `note`; `--append`'s explicit
"kept, as asked" lines.

## Recommended edits

1. `prompts/batch-B2-TEST.md:33` — replace `sorted(glob(...))[-1]` with the ledger query in §4 above.
2. `prompts/batch-B2-TEST.md:27` — drop the `sk-` grep or scope it to `--include=*.py -I` minus `src/security/`.
3. `src/cli/main.py:548` — `--queue` help → `default: data/gate.jsonl (from company.yaml approval.queue)`.
4. Optional: `run` could route blocked-input runs to a scratch root like `demo/run.sh` does (F3).