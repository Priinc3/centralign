# Video script — 75 seconds, one take

Audience: an evaluator who has the GitHub link and will run `bash demo/run.sh` afterwards.
Everything below is real output from a cold run, offline, on a laptop with no API key.

**Before you record (30s):** `bash demo/run.sh` once so the terminal font is settled, and
`clear` + scrollback reset. Set the window to ~110×32 so nothing wraps.

**Record:** `rm -rf /tmp/vid && bash demo/run.sh /tmp/vid`, then `bash demo/run.sh /tmp/vid --append`.
Nothing is edited afterwards — if a beat glitches, cut and re-take the take.

---

### 0:00 — the ask (5s)

`bash demo/run.sh /tmp/vid`

> "Find the latest invoice from Company X and post it to the ERP." That's the whole brief. No
> API key, no internet, no browser install — the only thing it talks to is a simulated ERP on
> 127.0.0.1 that the command starts and stops itself.

### 0:05 — the seed (5s)

```
seed        3 files in data/seed/invoices, newest = CX-2024-0912 $4,820.00 due 2024-10-12
erp rows    0
task        find latest invoice from Company X and post it to the ERP
```

> Three invoices on disk, an empty ERP. The run starts from nothing every time, so what you see
> is the work, not a warm cache.

### 0:10 — the read, and the stop (10s)

```
run 1  1539a7fa5c65
  ✓ s1  invoice_find_latest    CX-2024-0912  $4,820.00 USD  due 2024-10-12
  ⏸ s2  erp_post_invoice       not posted — waiting for a human to approve it (queued below)
```

> It picked the newest invoice *for this company* and stopped before posting. Four thousand
> eight hundred and twenty dollars is over the company's one-thousand-dollar unattended limit,
> so the policy says a human signs off first. It didn't guess, and it didn't push through.

### 0:20 — the approval (8s)

```
1 approval needed before this can continue:
  ✓ 004e34e78f2b  erp_post_invoice $4,820.00  approved by demo-operator   (erp_post_invoice requires approval)
```

> The approval request is written to a queue with the amount on it, and signing it records a
> name. In the demo the name is passed as a flag; run it without that flag and it waits for a
> human and prints the exact command to approve. That name is in the audit trail either way.

### 0:28 — the verified post (12s)

```
run 2  continuing 1539a7fa5c65  (new run id: the ledger is append-only)
  ↻ s1  invoice_find_latest    CX-2024-0912  $4,820.00 USD  due 2024-10-12
  ✓ s2  erp_post_invoice       ERP row #1 created

verdict: pass 8/8   replayed=1   plan: heuristic   run: c46011299453
ERP count: 1
```

> It continued as a *new* run id — the ledger is append-only, so a run is never rewritten. The
> find step replayed from the idempotency index instead of re-reading. Then an independent
> verifier graded eight predicates against the ledger rows — not against what the executor says
> it did. `plan: heuristic` means the LLM planner wasn't needed: no key, deterministic plan.

### 0:40 — the replay (10s)

`bash demo/run.sh /tmp/vid --append`

```
run 1  32d361dade01
  ↻ s1  invoice_find_latest    CX-2024-0912  $4,820.00 USD  due 2024-10-12
  ↻ s2  erp_post_invoice       ERP row #1 created

verdict: pass 8/8   replayed=2   plan: heuristic   run: 32d361dade01
ERP count: 1  (unchanged: nothing was double-posted)
```

> Same task, same scratch. Nothing executed — `replayed=2` — and the ERP still holds exactly one
> row. A pass served from the ledger is a different claim from a pass that executed, so the CLI
> tells you which one you got without you opening anything.

### 0:50 — the evidence (15s)

`cat /tmp/vid/runs/*/evidence.json | head -30`

> Every run leaves its plan, every step row with the args the tool really got, every event, and
> the verdict. If a tool did not run, the bundle says so — no silent mock autonomy.

### 1:05 — the checks (10s)

`python3 -m src.security.scan` then `python3 -m pytest tests/ -q`

```
findings: 0  → safe to publish
127 passed, 1 skipped in 7.36s
```

> One command proves the tree has no credentials in it, that the allowlist and path sandbox
> still refuse what they must, and that the redactor still masks a secret — including a positive
> control, because "we found nothing" only means something if the scanner can find something.
> One hundred and twenty-seven tests, offline, no API key.

### 1:15 — close (5s)

> Invoice intake, one company profile, done for real: planned, executed, gated by a human,
> verified from the ledger, and evidenced. That's CentrAlign — README has the architecture, the
> limits, and what's next.

---

**Total ≈ 75s.** If you are over 90s, cut the "evidence" beat to 8s and the close to 3s — never
cut the approval beat or the replay beat; those two are the difference between an agent demo and
an agent you can trust.

**If something breaks on camera:** nothing is interactive — the demo is one command. If it fails,
keep the frame: `python3 -m src.cli.main doctor` prints the failing check and the command that
fixes it, which is itself a good 10 seconds. Worst case, the repo is the submission; re-take.

---

## Verified transcript — every quote above re-checked against a fresh run

Phase 08 re-ran the demo cold and appended, and every quoted line in this script is copied from
that run. **Run ids and the ERP port are different on every run** (they are random and
`free_port`), so *your* ids on camera will not match these — that is correct behaviour, not drift.
What must match is the shape: same steps, same `replayed=` numbers, same counts. The `7.36s` on
the test line is also one measured run; yours will be a few tenths either side, and the count
`127 passed` is the part that must not move.

```
$ rm -rf /tmp/vid && bash demo/run.sh /tmp/vid
CentrAlign demo · scratch /tmp/vid · offline, no API key needed
CentrAlign · AI operator for invoice intake · offline, no API key needed
seed        3 files in data/seed/invoices, newest = CX-2024-0912 $4,820.00 due 2024-10-12
fresh       /tmp/vid/sim.db  (empty ERP db)
sim ERP     http://127.0.0.1:49251  db=/tmp/vid/sim.db  (started for this run, stopped when it ends)
fresh       /tmp/vid/runs  (run root)
fresh       /tmp/vid/gate.jsonl  (approval queue)
erp rows    0
task        find latest invoice from Company X and post it to the ERP

run 1  1539a7fa5c65
  ✓ s1  invoice_find_latest    CX-2024-0912  $4,820.00 USD  due 2024-10-12
  ⏸ s2  erp_post_invoice       not posted — waiting for a human to approve it (queued below)

1 approval needed before this can continue:
  ✓ 004e34e78f2b  erp_post_invoice $4,820.00  approved by demo-operator   (erp_post_invoice requires approval)

run 2  continuing 1539a7fa5c65  (new run id: the ledger is append-only)
  ↻ s1  invoice_find_latest    CX-2024-0912  $4,820.00 USD  due 2024-10-12
  ✓ s2  erp_post_invoice       ERP row #1 created

verdict: pass 8/8   replayed=1   plan: heuristic   run: c46011299453
ERP count: 1
evidence: /tmp/vid/runs/c46011299453/evidence.json
next: bash demo/run.sh --append   # same scratch, same task: watch replayed=2

$ bash demo/run.sh /tmp/vid --append
erp rows    1
task        find latest invoice from Company X and post it to the ERP

run 1  32d361dade01
  ↻ s1  invoice_find_latest    CX-2024-0912  $4,820.00 USD  due 2024-10-12
  ↻ s2  erp_post_invoice       ERP row #1 created

verdict: pass 8/8   replayed=2   plan: heuristic   run: 32d361dade01
ERP count: 1  (unchanged: nothing was double-posted)
next: python3 -m src.cli.main demo   # again without --append: a cold run

$ python3 -m src.security.scan
findings: 0  → safe to publish

$ python3 -m pytest tests/ -q
127 passed, 1 skipped in 7.36s
```

Wall-clock for the cold demo, measured at recording time: **0.427s** (`--append`: 0.323s).

---

## RECORDING.md — the shoot

One take, 75–90s, terminal only, no browser, no cut-and-paste mid-take.

**Terminal.** 110×32. Anything narrower wraps the step lines and a wrapped run looks like a bug.
Clear scrollback and a dark background; no editor or file manager open behind it.

**Before you press record, run these once so nothing is cold on camera:**

```bash
python3 -m src.cli.main doctor    # confirms deps + seed; if a check fails, fix it now
bash demo/run.sh /tmp/warm        # warms the sim + import path; this is the throwaway
```

**The take, in this exact order** (clearing between blocks so each beat starts at the top):

| # | keystrokes | what it proves | beat |
|---|---|---|---|
| 1 | `rm -rf /tmp/vid` | a truly cold scratch, no warm cache | the ask |
| 2 | `bash demo/run.sh /tmp/vid` | the read, the stop, the approval, the post, the verdict | read / approval / post |
| 3 | `bash demo/run.sh /tmp/vid --append` | `replayed=2`, ERP count still 1 | replay |
| 4 | `cat /tmp/vid/runs/*/evidence.json \| head -30` | the bundle is real, per run | evidence |
| 5 | `python3 -m src.security.scan` | `findings: 0` | checks |
| 6 | `python3 -m pytest tests/ -q` | `127 passed, 1 skipped` | checks |

Run 1–3 in one continuous screen (that *is* the demo). 4–6 can be a second continuous screen.
Narrate over the output as it appears — the point is that you are reading real numbers, so if you
lose your place, say the number that is on screen rather than finishing the sentence from memory.

**Timing.** The commands take ~1s total; the 75s is narration. Land the beats on the timestamps at
the top of this script. If you run long, cut the **evidence** beat to 8s and the close to 3s.
Never cut **approval** or **replay** — those two are the difference between an agent demo and an
agent you can trust. You may hard-cut between blocks 3/4/5/6; you may not cut inside a run.

**Upload.** Upload it unlisted (anyone with the link, not listed on your profile) — the grader
needs it, the world does not. Then paste the URL into `SUBMISSION.md` line 8 and tick the
checkboxes at the bottom: `VIDEO_URL: <fill after upload>`. Do the same for the repo URL
(`GITHUB_URL: <fill after push>`) after `git push` — see `prompts/phase-08-submission/USER-STEPS.md`.

**The honest caveat, if you want to say it on camera:** `plan: heuristic` means no key was needed —
the LLM planner exists and the multi-key router was proven live, but this particular run is the
deterministic fallback. Say that; do not let the viewer assume a model drove it.