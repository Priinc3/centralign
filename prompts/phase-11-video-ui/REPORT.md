# REPORT — Phase 11 video-on-UI rewrite (NORMAL, docs-only)

Type NORMAL, no siblings. Ran after 10. Three files touched, all markdown, exactly the BUILD
exception: `demo/video-script.md` (full rewrite to the UI), `README.md` (UI-first run + `127→133`),
`SUBMISSION.md` (numbers only). No engine file, no test file, no `src/ui/` file, no `context/*.yaml`,
not `docs/USER-TEST.md`, not `prompts/phase-08-submission/USER-STEPS.md` (read-only this phase).

```
$ git diff --stat README.md SUBMISSION.md demo/video-script.md
 README.md            |  42 +++--
 SUBMISSION.md        |   8 +-
 demo/video-script.md | 442 ++++++++++++++++++++++++++++++++++-----------------
 3 files changed, 337 insertions(+), 155 deletions(-)
```

---

## 1. Every quote in the script, traced to a run

The BUILD allows driving the page over HTTP when there is no display. I did exactly that — the
same way `tests/test_ui_offline.py` does — so every line quoted in the script came out of a
`/api/state` payload or the terminal, not out of a guess.

| script beat | quoted | source |
|---|---|---|
| 0:00 open | `fresh`/`reset` lines, `sim ERP http://127.0.0.1:53473 …`, `CentrAlign demo UI http://127.0.0.1:53476`, `planner heuristic (offline, no key needed)`, `scratch … wiped on start`, `ctrl-c stops the page and the sim ERP` | terminal, captured at `/tmp/cold.log` — pasted into the script |
| 0:05 the run | `press Run`, `working…`, `STEPS (2)`, `✓ s1 · invoice_find_latest` / `CX-2024-0912  $4,820.00 USD  due 2024-10-12`, `⏸ s2 · erp_post_invoice` / `not posted — waiting for a human to approve it (the card beside this list)`, `blocked / 7/8 predicates passed`, `0 rows in the ERP` | poll 1: `phase awaiting`, banner field `blocked / 7/8 predicates passed`, `erp.count 0`, steps `succeeded`/`skipped` with those exact `detail` strings |
| 0:25 approval | `erp_post_invoice · $4,820.00`, `(erp_post_invoice requires approval)`, `Request <id> is queued. Nothing is posted until someone presses Approve — the decision is written to the audit trail with their name.`, `[ your name ]` / `[ Approve ]` | the card copy is literal in `src/ui/index.html:153-155`; `pending[0]` confirmed `06f95a7b105a  erp_post_invoice  4820.0  reason=erp_post_invoice requires approval` |
| 0:37 post | `pass 8/8   replayed=1`, both step rows (`↻` replayed-from-the-ledger wording, `✓ ERP row #1 created`), `1 row in the ERP` + id/vendor/invoice/amount/due/from, evidence `events 10`, `tools executed: erp_post_invoice`, `tools replayed: invoice_find_latest`, `predicates 8/8 passed`, `evidence.json (the whole bundle)` | poll 2: banner recomputed client-side from 8/8 predicates and 1 `cached` step; `erp.row` dumped verbatim; `evidence.totals` = `{events: 10, tools_actually_executed: ["erp_post_invoice"], tools_replayed: ["invoice_find_latest"]}` |
| 0:49 replay | `Run again (run 2)`, `pass 8/8   replayed=2`, both steps ↻, `1 row in the ERP` unchanged, `events 8`, `tools executed: none`, `tools replayed: erp_post_invoice, invoice_find_latest` | poll 3 after `POST /api/run`: `clicks: 2`, `run_id 6d8ab17d18d8`, 2 `cached` steps, `erp.count 1`, `row.id 1`, `tools_actually_executed: []` |
| 1:01 checks | `findings: 0  → safe to publish`, `133 passed, 1 skipped in 11.28s` | both commands run, output pasted into the script |

**Two things I checked that the page shows, and got wrong on my first draft.** Both are in the
script now as the operator should see them, not as I assumed them:

- **The idle ERP panel reads `the sim ERP is not answering`, not `nothing posted yet`.** The
  latter is only the static HTML default at `src/ui/index.html:85`, visible for the fraction of a
  second before the first poll returns. `Demo.state()` returns early at idle (`src/ui/app.py:232`)
  so `erp` is `null` and `renderErp` takes its empty branch. Confirmed against a live idle
  `/api/state`. It flips to `0 rows in the ERP` as soon as a run starts.
- **`working…` may never render.** The page polls at 500ms and a cold run takes ~0.4s, so the
  `running` phase usually passes between two polls. The script tells the operator the amber banner
  is normally the first thing they see, rather than cueing narration for a frame that isn't there.

Also quoted and verified: `GET / -> 200  11682 bytes  0.001857s`, `POST /api/run -> 202`,
`POST /api/approve -> 200` with the granted decision (`approver: demo-operator`, `queue: closed`),
and the awaiting-state evidence panel (`events 10`, `executed: invoice_find_latest`,
`replayed: none`, `predicates: 7/8 passed`) — that panel is already populated while blocked, which
matches 09's screenshot description.

**The raw session** — page up on `53476`, sim ERP on `53473`, cold `/tmp/centralign-ui`:

```
$ python3 -m src.ui.app --port 0
fresh       /tmp/centralign-ui/sim.db  (empty ERP db)
fresh       /tmp/centralign-ui/runs  (run root)
fresh       /tmp/centralign-ui/gate.jsonl  (approval queue)
sim ERP     http://127.0.0.1:53473  db=/tmp/centralign-ui/sim.db  (started for this page, stopped with it)

CentrAlign demo UI  http://127.0.0.1:53476
task    find latest invoice from Company X and post it to the ERP
planner heuristic (offline, no key needed)
scratch /tmp/centralign-ui  (wiped on start; rerun for a cold pass 8/8)
ctrl-c stops the page and the sim ERP
```

```
$ GET  /             -> 200  11682 bytes  0.001857s
$ POST /api/run      -> 202  {phase: running, clicks: 1}

poll 1   phase awaiting | banner: blocked / 7/8 predicates passed | erp rows: 0
         s1 succeeded  -- CX-2024-0912  $4,820.00 USD  due 2024-10-12
         s2 skipped    -- not posted — waiting for a human to approve it (the card beside this list)
         pending: 06f95a7b105a  erp_post_invoice  4820.0  (erp_post_invoice requires approval)

$ POST /api/approve  {"request_id": "06f95a7b105a", "approver": "demo-operator"}  -> 200
         {ts: 2026-10-02T17:22:25+05:30, tool: erp_post_invoice, verdict: granted,
          reason: erp_post_invoice requires approval, risk: write, amount: 4820.0,
          request_id: 06f95a7b105a, queue: closed, approver: demo-operator}

poll 2   phase done | banner: pass 8/8   replayed=1  | erp rows: 1
         ↻ s1  invoice_find_latest    CX-2024-0912  $4,820.00 USD  due 2024-10-12
         ✓ s2  erp_post_invoice       ERP row #1 created
         evidence  /tmp/centralign-ui/runs/6c82c2832a4c/evidence.json
                   events 10 · executed: erp_post_invoice · replayed: invoice_find_latest
                   predicates 8/8 passed · run.plan_source: heuristic

$ POST /api/run      -> 202  {phase: running, clicks: 2}

poll 3   phase done | banner: pass 8/8   replayed=2  | erp rows: 1 (row id still 1)
         ↻ s1  invoice_find_latest    CX-2024-0912  $4,820.00 USD  due 2024-10-12
         ↻ s2  erp_post_invoice       ERP row #1 created
         evidence  /tmp/centralign-ui/runs/6d8ab17d18d8/evidence.json
                   events 8 · executed: none · replayed: erp_post_invoice, invoice_find_latest
                   predicates 8/8 passed
```

ERP row read straight out of `/api/state` — this is what the page's ERP panel renders:

```
count 1
{"id": 1, "idempotency_key": "inv-8e41e8ea926c4efb4a4836cb", "vendor": "ACME SUPPLY CO.",
 "company": "Company X", "invoice_number": "CX-2024-0912", "amount": "4820.00",
 "currency": "USD", "due_date": "2024-10-12", "source_file": "INV-X-2024-0912-acme.pdf"}
```

### One correction to 09's transcript, and why the script hedges

09's REPORT shows the startup block as three `fresh` lines. That is right on a machine that has
never run the page; on any re-record `sim.db` exists, so `cli.fresh` prints `reset` plus
`scratch only — undo = recreate with: bash demo/run.sh` (`src/cli/main.py:418-420`). I captured
both and the script tells the camera operator that either is correct, so nobody burns a take on it.

```
=== cold (dir does not exist) ===        === re-record (dir now exists) ===
fresh       …/sim.db  (empty ERP db)     reset       …/sim.db  (empty ERP db)
fresh       …/runs  (run root)                      scratch only — undo = recreate with: bash demo/run.sh
fresh       …/gate.jsonl  (approval queue) fresh     …/runs  (run root)
```

## 2. Numbers — `127 → 133`

```
$ grep -rn "127 passed\|127 tests" README.md SUBMISSION.md demo/
$ echo $?
1
```

Empty, which is the BUILD's criterion. Every remaining `127` in the publishable docs is `127.0.0.1`:

```
README.md:19,23,27,139,188 · SUBMISSION.md:22 · demo/script.md:4 · demo/video-script.md:27,29,37,214,216
```

Twelve edits: `README.md` ×4 (quickstart count, repo layout, `Proven not claimed`, ~7s → ~11s),
`SUBMISSION.md` ×3, `demo/video-script.md` ×5. The pinned `7.36s` is gone from every doc that had
it — 10's REPORT flagged it as per-machine wall clock, and the script now keeps `11.28s` but labels
it: *"one measured run on a laptop; yours will be a few tenths either side. The count `133 passed` is
the part that must not move."*

## 3. README — UI-first, terminal as alt

The Quickstart is now `### Watch it run (the UI)` → `### Or run it from the terminal (same loop, no
browser)`. The terminal section keeps its real transcript, byte for byte. Three additions that
earn their lines: `--llm` and the localhost-only refusal next to the UI command; `tests/
test_ui_offline.py` in the "tells you more" list, because it is the proof the page needs no browser;
`src/ui/` in the repo layout; and a UI line in `Proven, not claimed`.

The 30-second pitch at the top is untouched — "runs in 0.4 seconds" is still the CLI's number and
is still true.

## 4. Script shape

| at | beat | s | camera |
|---|---|---|---|
| 0:00 | open — `--port 0`, URL prints | 5 | terminal, full |
| 0:05 | the run — click Run, steps, amber banner | 20 | browser full 1280×800 |
| 0:25 | the approval — type name, click Approve | 12 | right card pushed in |
| 0:37 | the verified post — green banner, ERP row, evidence | 12 | full frame, hold the banner |
| 0:49 | the replay — Run again, `replayed=2` | 12 | full frame |
| 1:01 | the checks — scan + suite | 12 | terminal, full |
| 1:13 | close | 10 | hold the green banner |

83s, inside both the BUILD's 75–100s and the posting's 75–90s. The BUILD's beat list and its order
are followed exactly; only the two 15s beats were stretched (+5 each) to clear 75s. Each beat names
where the camera points, as asked.

**10's closing beat is byte-identical** — copied in, not retyped:

```
$ grep -n "Invoice intake, one company profile" -A 10 demo/video-script.md
174:> Invoice intake, one company profile, done for real: planned, executed, gated by a human, verified
175-> from the ledger, and evidenced. That's CentrAlign.
176->
177-> I built this as my **Intern** submission — a narrow invoice flow that genuinely runs. The same
178-> runtime also carries the **Founding**-scope pieces: frozen contracts, the append-only ledger, the
179-> independent verifier, the multi-key router — happy to go deep on any of those live.
180->
181-> README has the architecture, the limits, and what's next.
```

**10's role line is untouched** at `SUBMISSION.md:3`, and `SUBMISSION.md`'s whole diff is three
number lines — the `Role:` line appearing as a `+` in `git diff` is phase 10's own work, still
uncommitted, not this phase's. Intern-first ordering survives everywhere:

```
$ grep -in "founding" SUBMISSION.md demo/video-script.md
SUBMISSION.md:3:Role: AI Engineering Intern (prototype also demonstrates Founding-scope architecture — see video close)
demo/video-script.md:178:> runtime also carries the **Founding**-scope pieces: frozen contracts, the append-only ledger, the
```

## 5. §RECORDING.md rewritten

Screen-record tool first, as asked: QuickTime *New Screen Recording* ⌘⌃Esc as the no-install default,
plus `screencapture -v -V95 /tmp/centralign-ui.mov` as the CLI equivalent — checked on this machine
(macOS 27.0.1, `-v` and `-V<seconds>` both present). Browser is 1280×800, 100%, full screen. Camera
table is per beat. Mic beats are a table keyed to the action, not to the clock — "say the number that
is on screen rather than finishing a sentence from memory."

The two never-cut beats are still approval and replay, per 10. The "cut if long" advice moved from
evidence (no longer a beat on this recording — the panel is the evidence now) to checks.

---

## Verify

```
$ python3 -m pytest tests/ -q
133 passed, 1 skipped in 11.31s

$ python3 -m src.security.scan
findings: 0  → safe to publish

$ grep -rn "127 passed\|127 tests" README.md SUBMISSION.md demo/
$ echo $?
1
```

## Findings this phase did not fix

- **The page's Evidence panel renders `planner: undefined`.** `src/ui/index.html:179` reads
  `run.plan_source` where `run` is the `/api/state` payload, which has no such key — the value is at
  `evidence.run.plan_source`, and it is `heuristic` (confirmed in poll 2 above). It will be visible
  on camera at 0:37, so the script names it in place and says *do not re-take for it*, rather than
  letting the operator burn a take. One-line fix in `src/ui/app.py`'s `state()`, out of scope for a
  docs-only BUILD. **This is the only reason a scripted beat is not fully clean.**
- **`POST /api/approve` echoes `decided_on` = the request id.** `decided_on` in the granted record
  (`06f95a7b105a`) is the id of the request, not of a decision — it looks like it should be a
  timestamp. Not quoted on camera; worth a look in `src/reliability/hitl.py`.
- **`docs/USER-TEST.md` still prints `127 passed, 1 skipped` (lines 367, 375).** Outside this
  BUILD's three files and outside its grep, so left alone — but it is the last publishable surface
  with the stale number. One-line fix whenever a BUILD grants it.

skipped: adding the UI to `SUBMISSION.md`'s "What a reviewer should run, in order" list — the BUILD
scoped that file to numbers only. Add when the packet is next opened for write; it is the one place
an evaluator is told what to run and currently does not mention the page.
