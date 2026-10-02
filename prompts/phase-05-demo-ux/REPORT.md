# REPORT — Phase 05 demo-ux (NORMAL, B2)

Ran 2026-10-02. Verdict: **PASS — `bash demo/run.sh` alone goes seeded invoice → approval → verified
ERP post → evidence in 0.45s wall, offline, with `replayed=N` on the verdict line.**

Four BUILD criteria plus the B1-F1/B1-F2 findings this phase carried. Nothing outside my OWN files
was edited: `src/runtime/*`, `src/ledger/*`, `src/tools/*`, `src/memory/*`, `src/policy/*`,
`src/reliability/*`, `src/verifier/*` and `context/*` are byte-identical to what I found.

## Files changed (my OWN files only)

| file | lines | what it is |
|---|---|---|
| `src/cli/main.py` | 585 | `demo` / `run` subcommands: live step progress off the ledger, the HITL gate, the verdict line, scratch-sim lifecycle |
| `src/cli/doctor.py` | 163 | one line per readiness check, exit 0 = ready offline |
| `demo/run.sh` | 38 | the one command: preflight `doctor`, then `demo` on a scratch root |
| `demo/script.md` | 100 | 30-second video narration, timed beats, every claim backed by the run above it |
| `tests/test_demo_offline.py` | 132 | 6 tests: cold 8/8, warm `replayed=2`, gate holds without a human, empty task, doctor offline, doctor browser |

No `src/ui/*`. One beautiful CLI beat a CLI + a static web page that shows the same JSON
(`ponytail` rung 1: does this need to exist at all?). The evidence bundle *is* the second view —
`cat runs/<id>/evidence.json` — and it is already part of the demo output.

## Criteria

| # | criterion | result |
|---|---|---|
| 1 | `rm -rf /tmp/d5 && bash demo/run.sh` → `verdict: pass 8/8`, `ERP count: 1`, `replayed` line, wall <60s | PASS — 0.454s wall |
| 2 | `python3 -m src.cli.main run --task ""` → `blocked / No task given` rc=1 | PASS |
| 3 | `python3 -m pytest tests/test_demo_offline.py -q` green; full suite stays green | PASS — 6 passed; 89 passed, 1 skipped |
| 4 | No network except localhost sim; offline + no-key prints `plan: heuristic` | PASS — first line at 54ms, planner source printed on the verdict line |

## Commands + raw output

### Criterion 1a — cold run (`rm -rf /tmp/d5` first)

```
$ rm -rf /tmp/d5 && time bash demo/run.sh /tmp/d5
CentrAlign demo · scratch /tmp/d5 · offline, no API key needed
CentrAlign · AI operator for invoice intake · offline, no API key needed
seed        3 files in data/seed/invoices, newest = CX-2024-0912 $4,820.00 due 2024-10-12
fresh       /tmp/d5/sim.db  (empty ERP db)
sim ERP     http://127.0.0.1:61009  db=/tmp/d5/sim.db  (started for this run, stopped when it ends)
fresh       /tmp/d5/runs  (run root)
fresh       /tmp/d5/gate.jsonl  (approval queue)
erp rows    0
task        find latest invoice from Company X and post it to the ERP

run 1  684b2bfd1361
  ✓ s1  invoice_find_latest    CX-2024-0912  $4,820.00 USD  due 2024-10-12
  ⏸ s2  erp_post_invoice       not posted — waiting for a human to approve it (queued below)

1 approval needed before this can continue:
  ✓ 9cb8d9c3db0f  erp_post_invoice $4,820.00  approved by demo-operator   (erp_post_invoice requires approval)

run 2  continuing 684b2bfd1361  (new run id: the ledger is append-only)
  ↻ s1  invoice_find_latest    CX-2024-0912  $4,820.00 USD  due 2024-10-12
  ✓ s2  erp_post_invoice       ERP row #1 created

verdict: pass 8/8   replayed=1   plan: heuristic   run: 3ffb58274f4f
ERP count: 1
evidence: /tmp/d5/runs/3ffb58274f4f/evidence.json
next: bash demo/run.sh --append   # same scratch, same task: watch replayed=2

bash demo/run.sh /tmp/d5  0.18s user 0.05s system 49% cpu 0.454 total
rc=0
```

Everything the BUILD asked to see is there: 8/8, one ERP row, `replayed=` on the verdict line,
`plan: heuristic`, and an approval that a named human signed. 0.454s wall against a 60s budget;
the target (<15s without a Playwright install) needs no install at all.

### Criterion 1b — warm run, nothing wiped (B1-F1)

```
$ bash demo/run.sh /tmp/d5 --append
kept        /tmp/d5/sim.db  (kept, as asked)
kept        /tmp/d5/runs  (kept, as asked)
kept        /tmp/d5/gate.jsonl  (kept, as asked)
erp rows    1

run 1  9de293b48674
  ↻ s1  invoice_find_latest    CX-2024-0912  $4,820.00 USD  due 2024-10-12
  ↻ s2  erp_post_invoice       ERP row #1 created

verdict: pass 8/8   replayed=2   plan: heuristic   run: 9de293b48674
ERP count: 1  (unchanged: nothing was double-posted)
evidence: /tmp/d5/runs/9de293b48674/evidence.json
rc=0
```

`replayed=2` is the B1-F1 fix: a reader can tell a replayed pass from an executed pass without
opening the bundle, and the ERP row count proves the replay posted nothing. Note there is no
approval this time — both steps replayed *before* the gate is consulted, so nothing needed signing.

### Criterion 1c — reproducibility without the manual `rm` (B1-F2)

The scratch wipe is the point of `--append` being opt-in. Three consecutive runs:

```
$ bash demo/run.sh | grep -E 'reset|verdict|ERP count'
reset       /tmp/centralign-demo/sim.db  (empty ERP db)
reset       /tmp/centralign-demo/runs  (run root)
reset       /tmp/centralign-demo/gate.jsonl  (approval queue)
verdict: pass 8/8   replayed=0   plan: heuristic   run: 6e01b47e5867
ERP count: 1
# (second run, no rm: identical, replayed=0 / count 1 — not a stale 8/8 out of a warm ledger)
# (third run with --append: replayed=2, count 1 unchanged)
```

The approval queue is wiped too, not just the ledger and the ERP: `hitl.ensure_request` deliberately
reuses a granted request for the same `(tool, amount, domain)`, so a "fresh" run that kept the queue
would silently post without ever asking a human again.

### Criterion 2 — empty task

```
$ python3 -m src.cli.main run --task "" ; echo rc=$?
CentrAlign · AI operator for invoice intake · offline, no API key needed
task        (empty)

run 1  4ae50c3e1aeb

verdict: blocked / No task given   replayed=0   plan: heuristic   run: 4ae50c3e1aeb
  ✗ non_empty_goal: No task given
  ✗ plan_has_steps: the plan contains at least one dispatchable step
evidence: runs/4ae50c3e1aeb/evidence.json
next: python3 -m src.cli.main demo   # the whole thing, one command, offline
rc=1
```

It goes through the loop rather than short-circuiting in the CLI: an empty goal is `blocked` with the
reason on record, and the exit code is 1. The last line is a way out, not a dead end.

### Criterion 3 — tests

```
$ python3 -m pytest tests/test_demo_offline.py -q
......                                                                   [100%]
6 passed in 1.65s

$ python3 -m pytest tests/ -q
........................................................................ [ 80%]
................s.                                                       [100%]
89 passed, 1 skipped in 6.95s
```

The `s` is the pre-existing Playwright skip. Nothing outside my file changed status.

### Criterion 4 — speed, offline, no key

```
$ python3 -c "... Popen(demo); read one line ..."
first line: CentrAlign · AI operator for invoice intake · offline, no API key needed
after 0.054s
```

The banner prints before any heavy import (every `pydantic`/`yaml`/`sqlite` import in this CLI is
inside the function that needs it), so the first feedback line is Python startup plus an f-string.

```
$ env -u OPENAI_API_KEY python3 -m src.cli.main doctor ; echo rc=$?
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
runs dir    ok     …/centralign/runs is writable
sim ERP     note   not running at http://127.0.0.1:8901 — the demo starts its own; or: python3 sim_app/server.py --port 8901 --db /tmp/sim.db
network     ok     not needed: no API key, no internet — only 127.0.0.1 is contacted

ready: the offline demo runs (python3 -m src.cli.main demo)
rc=0
```

No sim running, no key, no Playwright → still ready. `pip install playwright` appears only under
`doctor --browser`, which is the only mode that needs it, and that mode exits 1 without it.

### The gate really is wired (BUILD "wire authorizer=hitl.authorizer")

Interactive TTY, through a real pty, no `--approve`:

```
CentrAlign · AI operator for invoice intake · offline, no API key needed
task        find latest invoice from Company X and post it to the ERP

run 1  4d648ad65fd3
  ✓ s1  invoice_find_latest    CX-2024-0912  $4,820.00 USD  due 2024-10-12
  ⏸ s2  erp_post_invoice       not posted — waiting for a human to approve it (queued below)

1 approval needed before this can continue:
  approve e89b8837cda1 erp_post_invoice $4,820.00 (erp_post_invoice requires approval)? [y/N] y
  ✓ e89b8837cda1  approved by princegondaliya

run 2  continuing 4d648ad65fd3  (new run id: the ledger is append-only)
  ↻ s1  invoice_find_latest    CX-2024-0912  $4,820.00 USD  due 2024-10-12
  ✓ s2  erp_post_invoice       ERP row #1 created

verdict: pass 8/8   replayed=1   plan: heuristic   run: 7aeb6f654e7f
rc = 0
```

Non-interactive, no `--approve`, nothing signed:

```
$ ERP_URL=http://127.0.0.1:8913 python3 -m src.cli.main run \
      --task "find latest invoice from Company X and post it to the ERP" \
      --runs /tmp/d14/runs --queue /tmp/d14/gate.jsonl --offline < /dev/null
  ✓ s1  invoice_find_latest    CX-2024-0912  $4,820.00 USD  due 2024-10-12
  ⏸ s2  erp_post_invoice       not posted — waiting for a human to approve it (queued below)

1 approval needed before this can continue:
  ⏸ 4e83e9f27bde  erp_post_invoice $4,820.00  waiting for a human   (erp_post_invoice requires approval)
      next: python3 -m src.reliability.hitl --approve 4e83e9f27bde --approver <you>
      then: python3 -m src.cli.main run --task "…" --runs /tmp/d14/runs --approve <you>

verdict: blocked / 7/8 predicates passed   replayed=0   plan: heuristic   run: 5f3e541ad926
rc=1

$ curl -s http://127.0.0.1:8913/invoices
{"count": 0, "invoices": []}
```

The one failing predicate is `criterion:s2` (weight 0), so the run reads `blocked / 7/8` — the
verifier's own summary, not a nicer one. The ERP has zero rows.

The test suite asserts the second case reaches the ERP zero times. The whole CLI wiring is one
`functools.partial(hitl.authorizer, path=queue)` handed to `run_task(authorizer=…)` — 01's HELP-5,
used, with no edit to the loop.

## Design decisions

**Progress comes from a reader thread, not a callback.** The loop is frozen and the ledger already
appends one row per attempt, so `Follower` polls that table every 40ms and prints each new row as it
appears. A resumed run's id only exists *after* `checkpoint.resume` starts, so the follower adopts
the newest run it has not already printed (`avoid`). Costs ~60 lines, buys a demo where you watch
the steps happen. `ponytail:` swap for a progress callback if the loop ever stops being frozen.

**A blocked run is continued, not retried, by the CLI.** `drive()` runs, and if the *only* thing in
the way is a queued approval it signs off (`--approve WHO`) or prompts, then re-enters via
`checkpoint.resume`. One continuation round, not a loop: if the second run is blocked again the CLI
prints what is still pending instead of retrying on its own.

**Approvals are scoped to the tools the run actually tried.** `data/gate.jsonl` in the repo holds 88
pending requests from Phases 03/04; settling "everything pending" made the empty-task run print 88
lines of other people's approvals. `settle()` reads the run's own `evidence.json` for its tool names
and only touches matching requests. That file is written before `run_task` returns, so it costs no
new plumbing.

**The scratch guard compares paths textually, not through `resolve()`.** On macOS `/tmp` is a symlink
to `/private/tmp`, so `Path.resolve().startswith("/tmp")` is False for every scratch path and the
demo silently kept a warm state — the exact B1-F2 trap, reintroduced by the guard meant to close it.
`os.path.abspath` + `/tmp` and `$TMPDIR` roots gets it right; `tests/test_demo_offline.py` would have
caught it (pytest's `tmp_path` is under `$TMPDIR`, not `/tmp`).

**A sim that is not ours is refused, not used.** `/health` reports the db it is serving, so
`wait_sim` compares it to the db we asked for. Without that check, `--port 8912` with something
already on 8912 posted the demo's invoice into a stranger's ERP:

```
sim ERP   port 8912 already serves another ERP (db=/tmp/d10.db) — next: drop --port 8912, or pass a free one
rc=1
```

**One display string is reworded.** The frozen executor words a gated step `blocked: approval
required (no approval channel in Phase 01)`, which this CLI makes untrue. The CLI translates it to
plain words at print time; `evidence.json` keeps the executor's sentence.

## Limits / known ceilings

- **`Follower` polls, so a run faster than 40ms prints after it finishes, not during.** Every real
  run here is 10–30ms, so "live progress" is really "one drain at the end, in the right order". It
  streams for real only when something is slow (an LLM plan, a downed ERP with backoff).
- **`replayed=N` counts cached steps in the final run only.** A two-run demo shows `replayed=1` (the
  find) even though the post also had an approval round-trip. `evidence.json` totals are per run by
  construction; a cross-run total would need a second ledger query and nobody reads it out loud.
- **One approval round-trip, never two.** If the resumed run needs a *different* approval, the CLI
  stops and prints the next command. A policy that queues a fresh request on every attempt would
  make this a loop.
- **`--approve WHO` is unattended sign-off.** It is the demo and CI path, and the name is recorded in
  the queue, but a CI run with the flag grants approvals without a person present. Interactive use
  should omit it and answer the prompt.
- **`hitl.ensure_request` keys on `(tool, amount, domain)`** (04's ceiling), so two genuinely
  different postings of the same amount share one request. Unchanged by this phase; still worth
  adding the invoice number to the key.
- **`doctor` reads the policy through `load_context()` but does not check the manifest registry
  loads.** A broken `src/tools` registry still shows green; the run itself then reports it.
- **The sim is a subprocess.** If this machine's python is not the one running the demo, `--port` and
  the db path can disagree; `wait_sim`'s db check is what catches it.
- **`demo/run.sh` refuses a scratch root outside `/tmp`**, and the CLI refuses to delete outside
  `/tmp`/`$TMPDIR`. On a machine where TMPDIR is unset and the user wants scratch elsewhere, pass
  `--runs`/`--db`/`--queue` to the CLI directly instead of through the script.

## Verify steps

```bash
cd <repo>

# 0. preflight: is this machine ready, offline?
python3 -m src.cli.main doctor ; echo rc=$?          # rc=0

# 1. the demo, cold, from nothing
rm -rf /tmp/d5 && time bash demo/run.sh /tmp/d5       # verdict: pass 8/8 · replayed=1 · ERP count: 1
bash demo/run.sh /tmp/d5 --append                     # verdict: pass 8/8 · replayed=2 · count unchanged

# 2. the edges the BUILD names
python3 -m src.cli.main run --task "" ; echo rc=$?    # blocked / No task given, rc=1
python3 -m src.cli.main run --task "find latest invoice from Company X and post it to the ERP" \
    --runs /tmp/d5/runs --queue /tmp/d5/gate.jsonl ; echo rc=$?   # waits for a human, ERP count 0

# 3. the suite
python3 -m pytest tests/test_demo_offline.py -q       # 6 passed
python3 -m pytest tests/ -q                           # 89 passed, 1 skipped

# 4. nothing leaked into the repo
stat -f "%Sm %N" data/gate.jsonl data/sim_erp.db      # unchanged: the demo writes only under the scratch root
pgrep -fl sim_app/server.py || echo "no sim left running"
```

## Help needed

None blocking. Two notes for whoever owns the frozen files, both optional:

1. `src/runtime/executor.py:144` still says *"blocked: approval required (no approval channel in
   Phase 01)"*. Phase 05 supplies the channel, so that sentence is now wrong in the error a user
   reads in `evidence.json`. One-word fix to `approval required (queued for a human)`; I translated
   it at the CLI instead because `src/runtime/*` is not mine.
2. `src/runtime/planner.py` hardcodes `base_url: ""` in `_INTAKE_POST_ARGS`, so the ERP endpoint can
   only arrive through `$ERP_URL`. Fine for the demo (`cmd_demo` sets it), but a `run` that needs two
   different ERPs in one process cannot express it. A `--erp-url` flag that threads a real value
   through the plan would fix it properly.
---

# FIX-1 — B2 polish F3/F4/F5 (info-level, no engine files touched)

Scope held: `src/cli/main.py`, `src/cli/doctor.py`, `tests/test_demo_offline.py`. No `src/runtime/*`
and no `src/verifier/*` edits — F3 was fixed by choosing the run root *before* `run_task` mkdirs,
which is the only place a run dir appears.

## F3 — a rejected ask no longer litters the repo

`run --task ""` used to create `runs/<id>/` in the repo tree for a verdict that is blocked before a
plan exists. Nothing downstream can be resumed from it, so it has no audit value.

`cmd_run` now routes the empty ask to scratch when `--runs` was *implied* rather than passed:

```python
runs = Path(args.runs or ROOT / "runs")
if args.runs is None and not task.strip():
    runs = SCRATCH / "runs"
    head("runs", f"{runs}  (empty ask: nothing to audit, so not under the repo's runs/)")
```

`--runs` stays authoritative: an explicit `--runs` is never rerouted, and a non-empty ask still
defaults to `runs/`. The empty ask is the *only* blocked-before-plan path — a tool that fails after a
real plan keeps its evidence in the repo, which is the point of the ledger. `runs/` was already
gitignored, and scratch is outside the tree entirely, so both destinations are ignored either way.

```
$ BEFORE=$(ls -1 runs/ | wc -l) && python3 -m src.cli.main run --task "" ; echo rc=$? ; AFTER=...
CentrAlign · AI operator for invoice intake · offline, no API key needed
runs        /tmp/centralign-demo/runs  (empty ask: nothing to audit, so not under the repo's runs/)
task        (empty)

run 1  145046ba3fe6

verdict: blocked / No task given   replayed=0   plan: heuristic   run: 145046ba3fe6
  ✗ non_empty_goal: No task given
  ✗ plan_has_steps: the plan contains at least one dispatchable step
evidence: /tmp/centralign-demo/runs/145046ba3fe6/evidence.json
next: python3 -m src.cli.main demo   # the whole thing, one command, offline
rc=1
repo runs/ entries: before=16 after=16
```

Same verdict, same rc, same two predicates — the run dir just lands somewhere disposable, and the
path is printed. New test `test_an_empty_ask_does_not_litter_the_repo_runs_dir` asserts the repo
listing is unchanged and the scratch path is printed. It is a real check: with the `if` condition
forced to `False` it fails on the evidence path being
`…/centralign/runs/1f837043a8de/evidence.json`, and passes again once restored.

## F4 — `--queue` help stops lying

It said `default: context/company.yaml`, which is the file the value is *read from*, not the queue.
`company.yaml: approval.queue = data/gate.jsonl`, which is what `hitl.queue_path()` actually returns:

```
$ python3 -m src.cli.main run --help
  --runs RUNS      run root dir (default: runs/)
  --queue QUEUE    approval queue file (default: data/gate.jsonl, from
                   company.yaml approval.queue)
```

`--runs` moved to `default=None` so `cmd_run` can tell "implied" from "passed" (that is what F3
keys on); the resolved default and its help text are unchanged.

## F5 — the doctor's sim ERP note no longer reads like a failure

```
- not running at {base} — the demo starts its own; or: python3 sim_app/server.py …
+ not running at {base} — fine: the demo starts its own per run; or: python3 sim_app/server.py …
```

`demo` binds a free port per run, so nothing is ever expected at 8901 — the note now says the
per-run port explicitly instead of implying a missing prerequisite. Still a `note`, never a `fail`,
so exit stays 0.

## Re-verified

```
$ python3 -m pytest tests/test_demo_offline.py -q
7 passed in 1.70s

$ python3 -m pytest -q
115 passed, 1 skipped in 7.07s

$ rm -rf /tmp/fx && bash demo/run.sh /tmp/fx
verdict: pass 8/8   replayed=1   plan: heuristic   run: c0842e60d11d
ERP count: 1
evidence: /tmp/fx/runs/c0842e60d11d/evidence.json
script rc=0

$ python3 -m src.cli.main doctor ; echo rc=$?
sim ERP     note   not running at http://127.0.0.1:8901 — fine: the demo starts its own per run; …
ready: the offline demo runs (python3 -m src.cli.main demo)
rc=0

$ python3 -m src.cli.main run --task "" --runs /tmp/expl   # explicit --runs still wins
evidence: /tmp/expl/bf73c7f93fb1/evidence.json
```

7 demo tests (6 + the F3 one), 115 across the suite, the pre-existing Playwright skip unchanged.
`--runs` regression checked explicitly: with the flag the empty ask writes to `/tmp/expl`, not to
scratch, so an operator who wants the evidence keeps it.
