# Demo script — 30 seconds, one take

Everything runs offline on a laptop: no API key, no internet, no browser install. The only thing
it talks to is a simulated ERP on `127.0.0.1` that the command starts and stops itself.

**Pre-flight (before you record, ~10s):** `bash demo/run.sh` once, so you know it is warm.
**Record:** `bash demo/run.sh` cold, then `bash demo/run.sh --append` for the replay beat.

Every block below is copied from a fresh cold run (`rm -rf /tmp/vid && bash demo/run.sh /tmp/vid`,
plus `--append`; transcript in [`video-script.md`](video-script.md)). **Run ids are random per run**
— yours will differ, and that is correct. The steps, `replayed=` numbers and counts must match.

---

### 0:00 — "is this machine ready?"

```bash
python3 -m src.cli.main doctor
```

> One command tells you whether this can run: Python version, dependencies, the policy numbers
> the gate will use, and the seed data. Missing Playwright is a *note*, not a failure — the demo
> uses files and the ERP, not a browser.

### 0:04 — the ask

```bash
bash demo/run.sh
```

> "Find latest invoice from Company X and post it to the ERP." That's the whole brief.

### 0:07 — the read (run 1)

Screen shows:

```
seed        3 files in data/seed/invoices, newest = CX-2024-0912 $4,820.00 due 2024-10-12
  ✓ s1  invoice_find_latest    CX-2024-0912  $4,820.00 USD  due 2024-10-12
  ⏸ s2  erp_post_invoice       not posted — waiting for a human to approve it (queued below)
```

> Three seeded invoices are on disk. It picked the newest one *for this company* and ignored the
> newer invoice that belongs to somebody else. The LLM is not driving this — the plan is a
> deterministic DAG, and every step prints what the tool actually returned.

### 0:12 — the approval

```
1 approval needed before this can continue:
  ✓ 004e34e78f2b  erp_post_invoice $4,820.00  approved by demo-operator   (erp_post_invoice requires approval)
```

> Posting money to the ERP needs a human. That's not a mock: the request is written to the
> approval queue, and `--approve demo-operator` signs it off with a name, so the audit trail
> records who. Run without that flag and it stops here and tells you the exact command to approve.

### 0:17 — the verified post (run 2)

```
run 2  continuing 1539a7fa5c65  (new run id: the ledger is append-only)
  ↻ s1  invoice_find_latest    CX-2024-0912  $4,820.00 USD  due 2024-10-12
  ✓ s2  erp_post_invoice       ERP row #1 created

verdict: pass 8/8   replayed=1   plan: heuristic   run: c46011299453
ERP count: 1
```

> It continued as a new run — the ledger is append-only, so a run id is never rewritten. The find
> step replayed from the idempotency index instead of re-reading, the post executed for real, and
> an independent verifier graded eight predicates against the ledger. Not the executor's word:
> the ledger rows.

### 0:24 — the replay (run it again)

```bash
bash demo/run.sh --append
```

```
  ↻ s1  invoice_find_latest    CX-2024-0912  $4,820.00 USD  due 2024-10-12
  ↻ s2  erp_post_invoice       ERP row #1 created

verdict: pass 8/8   replayed=2   plan: heuristic   run: 32d361dade01
ERP count: 1  (unchanged: nothing was double-posted)
```

> Same task, same scratch: nothing executed, `replayed=2`, and the ERP still holds exactly one row.
> A pass served from the ledger is not the same claim as a pass that executed, so the CLI prints
> which one you got — a reader never has to open the evidence bundle to tell.

### 0:28 — the evidence

```bash
cat /tmp/centralign-demo/runs/*/evidence.json | head -40
```

> Every run leaves `evidence.json` (plan, step rows, every event, the verdict, and the exact
> tools that executed) plus `events.jsonl` and `state.json`. If a tool did not run, the bundle says
> so — no silent mock autonomy.

---

**If something goes wrong on camera:** `doctor` prints the failing line *and* the command that
fixes it. There is no dead end: every blocked run ends with the next command to type.