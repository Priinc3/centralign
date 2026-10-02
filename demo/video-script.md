# Video script — 83 seconds, one take, on the UI

Audience: an evaluator who has the GitHub link and will run the demo afterwards.
Everything quoted below is copied from a live session of the page, driven over HTTP with no
browser, on a laptop with no API key. The numbers are real: `pass 8/8`, `replayed=1`,
`replayed=2`, `1 row`, `163 passed, 1 skipped`.

The story is three clicks in a browser: **Run → Approve → Run again.** The terminal only opens
and closes the show.

**Before you record (30s):** start the page once and close it (`python3 -m src.ui.app --port 0`,
then ctrl-c) so the sim ERP import path is warm. Then open the browser at **1280×800** and do one
full dry cycle — Run, Approve, Run again — so the takes are muscle memory. `ctrl-c` and restart
before the real take: scratch is wiped at startup, so the take starts cold.

---

### 0:00 — open (5s)

**Camera: terminal, full frame.** Nothing else on screen behind it.

```
$ python3 -m src.ui.app --port 0
fresh       /tmp/centralign-ui/sim.db  (empty ERP db)
fresh       /tmp/centralign-ui/runs  (run root)
fresh       /tmp/centralign-ui/gate.jsonl  (approval queue)
sim ERP     http://127.0.0.1:53473  db=/tmp/centralign-ui/sim.db  (started for this page, stopped with it)

CentrAlign demo UI  http://127.0.0.1:53476
task    find latest invoice from Company X and post it to the ERP
planner online — the page names the model that planned the run, or why it could not
scratch /tmp/centralign-ui  (wiped on start; rerun for a cold pass 8/8)
ctrl-c stops the page and the sim ERP
```

> One command brings up a real page on localhost. No install, no API key, no internet, and the
> only thing it talks to is a simulated ERP on 127.0.0.1 that the command started. The scratch
> wipes on startup, so what you see next is the work, not a warm cache.

> **On the `fresh` lines.** On a machine that has never run the page it prints `fresh`; on a
> re-record the first line reads `reset` plus `scratch only — undo = recreate with: bash
> demo/run.sh`. Both are correct and both are fine on camera — it is the wipe being honest about
> finding something. Ports and ids are random every run; that is `free_port`, not drift.

### 0:05 — the run (20s)

**Camera: browser, full frame at 1280×800.** Cursor is in shot. Move deliberately.

The page opens on: title `CentrAlign · an AI employee for invoice intake`, a **How it works** strip
reading `goal → understand → plan → execute → observe → adapt → verify → complete` (every chip dark —
the run has not started), a **Pick a job** gallery of three cards with the first selected, the task in
a mono strip, a grey banner reading **`press Run`**, `STEPS` with `no steps yet — press Run`,
`ERP ROW` reading `the sim ERP is not answering`, and the right card `no approval is waiting`.

> That ERP line is not a fault to worry about: before the first Run there is no run to ask the ERP
> about, so the page shows its empty state. It flips to `0 rows in the ERP` the moment you click.

**Click `Run the task`.** The page polls every 500ms and the run itself takes ~0.4s, so the amber
banner is usually the *first* thing you see — `working…` may flash past or never render. Either
way, within a second the steps land, and the strip fills in behind them:

```
HOW IT WORKS  goal → understand → plan → execute → observe → (adapt) → VERIFY → (complete)
THE PLAN      model fallback: LlmError: no usable LLM key: set GEMINI_API_KEY or
              OPENAI_API_KEY in the environment, deterministic planner used
              goal: find latest invoice from Company X and post it to the ERP
              s1 · invoice_find_latest     find the latest invoice for the company
              s2 · erp_post_invoice        post the invoice the find step returned to the ERP
```

In the strip, plain names are stages the run has been through, the filled one is where it is now,
and `(brackets)` are stages it never entered — `adapt` only runs on a retry, and `complete` waits
for the approval you are about to give. The badge under it is the run's own `plan_source`, and this
page has no offline mode: it asks the model on every run. On a keyed machine that line reads
`llm · gemini/gemma-4-31b-it`. **Check which one you got before you record** — if it says
`model fallback: …`, say so out loud instead of letting anyone assume a model drove it.

Under the strip, the **Pick a job** gallery — three cards, each stating the tool chain and the gate
before you touch it. The first is selected and this take runs it:

```
Post the latest invoice            find the latest invoice for Company X → post it to the ERP
                                   one approval: the ERP post
Summarize the invoice inbox        list seed/invoices → parse the two files it names → report the inbox
                                   read-only: no approval, nothing posted
Check the latest invoice, post nothing
                                   find the latest invoice for Company X → report it, write nothing
                                   read-only: no approval, nothing posted
```

> Three jobs, not one trick: the other two are read-side — they list and parse, and they change the
> plan because the ask changed, so nothing needs approving. They are on the page so you can click
> them after this take; `pass 9/9` and `pass 7/7`, both with zero approvals and zero ERP rows.

```
STEPS (2)
  ✓ s1 · invoice_find_latest
      CX-2024-0912  $4,820.00 USD  due 2024-10-12
  ⏸ s2 · erp_post_invoice
      not posted — waiting for a human to approve it (the card beside this list)
```

and the banner reads:

```
blocked / 7/8 predicates passed
```

`ERP ROW` flips from `the sim ERP is not answering` to `0 rows in the ERP`.

> Same brief as the CLI demo: find the latest invoice from Company X and post it to the ERP. It
> picked the newest invoice *for this company* and then stopped before posting. Four thousand
> eight hundred and twenty dollars is over this company's one-thousand-dollar unattended limit, so
> the policy says a human signs off first. It didn't guess, and it didn't push through. That
> amber banner is the verifier — one predicate short, from the ledger.

### 0:25 — the approval (12s)

**Camera: push in on the right card** (or leave full frame and just narrate — both read fine).

The right card is amber and names the request:

```
erp_post_invoice · $4,820.00        (erp_post_invoice requires approval)

Request 06f95a7b105a is queued. Nothing is posted until someone presses Approve —
the decision is written to the audit trail with their name.

[ your name ]        [ Approve ]
```

**Type a name, click the green `Approve`.** The card disappears on the next poll.

> The request was written to a queue with the amount on it. I type my name and press Approve, and
> that name goes into the audit trail — leave the box blank and it records the signed-in user
> instead, so an approval is never unowned. This is the same gate the CLI stops at; here it has a
> button, because a page should not ask you to copy a command line.

### 0:37 — the verified post (12s)

**Camera: full frame.** The banner is the hero shot — hold it.

```
pass 8/8   replayed=1
```

```
STEPS (2)
  ↻ s1 · invoice_find_latest
      replayed from the ledger (not called again) · CX-2024-0912  $4,820.00 USD  due 2024-10-12
  ✓ s2 · erp_post_invoice
      ERP row #1 created
```

```
ERP ROW      1 row in the ERP
  id 1 · vendor ACME SUPPLY CO. · invoice CX-2024-0912
  amount 4820.00 · due 2024-10-12 · from INV-X-2024-0912-acme.pdf
```

The right card's Evidence panel fills in: `file` the run's `evidence.json` path, `planner heuristic`,
`events 10`, `tools executed: erp_post_invoice`, `tools replayed: invoice_find_latest`,
`predicates: 8/8 passed`, and a collapsed `evidence.json (the whole bundle)` you can click open.

> Green. Eight of eight predicates, graded by an independent verifier against the ledger rows —
> not against what the executor says it did. The find step shows ↻ because it replayed from the
> idempotency index instead of re-reading the files. And the ERP really has one row in it: that
> panel is read out of the sim ERP over HTTP, not typed into the page.

> The `planner` row and the badge above the plan read the same field — the run's own
> `plan_source`, and there is no offline mode on this page to hide behind: it asks the model on
> every run. With a key exported the badge names the model that wrote the plan
> (`llm · gemini/gemma-4-31b-it`); with no key it names the reason it fell back. There is no badge
> on this page that a model did not earn.

### 0:49 — the replay (12s)

**Camera: full frame.** The Run button now reads **`Run again (run 2)`**.

**Click it.** The banner re-renders in place:

```
pass 8/8   replayed=2
```

Both steps are now ↻, including `s2 · erp_post_invoice · ERP row #1 created`, and `ERP ROW` still
reads `1 row in the ERP`. The Evidence panel now says `events 8`, `tools executed: none`,
`tools replayed: erp_post_invoice, invoice_find_latest`.

> Second click, same task, same scratch. Nothing executed — `replayed=2` — and the ERP still holds
> exactly one row. Nothing was double-posted, and the page tells you which claim you're looking
> at: a pass served from the ledger reads differently from a pass that executed. You don't have
> to open the bundle to tell.

### 1:01 — the checks (12s)

**Camera: terminal, full frame.** `ctrl-c` the page, then the two commands back to back.

```
$ python3 -m src.security.scan
findings: 0  → safe to publish

$ python3 -m pytest tests/ -q
163 passed, 1 skipped in 15.32s
```

> One command proves the tree has no credentials in it, that the allowlist and path sandbox still
> refuse what they must, and that the redactor still masks a secret — including a positive
> control, because "we found nothing" only means something if the scanner can find something. One
> hundred and sixty-three tests, offline, no API key, and ten of them drive this page over HTTP
> with no browser at all.

### 1:13 — close (10s)

> Invoice intake, one company profile, done for real: planned, executed, gated by a human, verified
> from the ledger, and evidenced. That's CentrAlign.
>
> I built this as my **Intern** submission — a narrow invoice flow that genuinely runs. The same
> runtime also carries the **Founding**-scope pieces: frozen contracts, the append-only ledger, the
> independent verifier, the multi-key router — happy to go deep on any of those live.
>
> README has the architecture, the limits, and what's next.

---

**Total ≈ 83s.** If you are over 90s, cut the **checks** beat to 8s — never cut the approval beat
or the replay beat; those two are the difference between an agent demo and an agent you can trust.

**If something breaks on camera:** keep the frame. Nothing here is scripted output — the page shows
real state. If the sim ERP really did fail to come up you get the same `the sim ERP is not
answering` line you saw on the idle page, now while a run is in flight, which is the difference;
clicking Run mid-run leaves the button disabled rather than starting a second one. `python3 -m
src.cli.main doctor` prints the failing check and the command that fixes it, which is itself a good
10 seconds. Worst case, the repo is the submission; re-take.

---

## Verified transcript — every quote above re-checked against a live session

Driven over HTTP against `python3 -m src.ui.app --port 0`, no browser, exactly the way
`tests/test_ui_offline.py` does it. Reproduced in
`prompts/phase-11-video-ui/REPORT.md` (the clicks) and `prompts/phase-13-ui-story/REPORT.md`
(the strip, the badge, the three cards, and the two read-side jobs).

**Run ids, the ERP port and the approval request id are different on every run** (random, and
`free_port`), so *your* ids on camera will not match these — that is correct behaviour, not drift.
What must match is the shape: same steps, same `replayed=` numbers, same counts, and `163 passed`
is the part that must not move.

### Terminal

```
$ python3 -m src.ui.app --port 0
fresh       /tmp/centralign-ui/sim.db  (empty ERP db)
fresh       /tmp/centralign-ui/runs  (run root)
fresh       /tmp/centralign-ui/gate.jsonl  (approval queue)
sim ERP     http://127.0.0.1:53473  db=/tmp/centralign-ui/sim.db  (started for this page, stopped with it)

CentrAlign demo UI  http://127.0.0.1:53476
task    find latest invoice from Company X and post it to the ERP
planner online — the page names the model that planned the run, or why it could not
scratch /tmp/centralign-ui  (wiped on start; rerun for a cold pass 8/8)
ctrl-c stops the page and the sim ERP
```

On a re-record the first line reads `reset` instead of `fresh`, with
`scratch only — undo = recreate with: bash demo/run.sh` under it.

### The three clicks

```
$ GET  /             -> 200  11682 bytes  0.001857s
$ POST /api/run      -> 202   {phase: running, clicks: 1}
```

Poll 1 — the page shows the amber banner and the queued request:

```
$ GET /api/state
  phase awaiting | banner: blocked / 7/8 predicates passed | erp rows: 0
  stages: goal, understand, plan, execute, observe, verify   (complete: not yet)
  plan_source: heuristic
  s1 succeeded  -- CX-2024-0912  $4,820.00 USD  due 2024-10-12
  s2 skipped    -- not posted — waiting for a human to approve it (the card beside this list)
  pending: 06f95a7b105a  erp_post_invoice  $4,820.00   (erp_post_invoice requires approval)
```

which the page paints as — the strip lit up to the stage it really reached, and the planner naming
itself above its own plan:

```
HOW IT WORKS  goal → understand → plan → execute → observe → (adapt) → VERIFY → (complete)
THE PLAN      model fallback: LlmError: no usable LLM key: set GEMINI_API_KEY or
              OPENAI_API_KEY in the environment, deterministic planner used
              goal: find latest invoice from Company X and post it to the ERP
              s1 · invoice_find_latest     find the latest invoice for the company
                                          done when: a parseable invoice for that company comes back
              s2 · erp_post_invoice        post the invoice the find step returned to the ERP
                                          done when: the ERP accepts the posted invoice
```

The click — a name goes in with the decision:

```
$ POST /api/approve  {"request_id": "06f95a7b105a", "approver": "demo-operator"}   -> 200
  {ts: 2026-10-02T17:22:25+05:30, tool: erp_post_invoice, verdict: granted,
   reason: erp_post_invoice requires approval, risk: write, amount: 4820.0,
   request_id: 06f95a7b105a, queue: closed, approver: demo-operator}
```

Poll 2 — after the approve, still inside the first click's cycle:

```
$ GET /api/state
  phase done | banner: pass 8/8   replayed=1   | erp rows: 1
  ↻ s1  invoice_find_latest    CX-2024-0912  $4,820.00 USD  due 2024-10-12
  ✓ s2  erp_post_invoice       ERP row #1 created
  evidence  /tmp/centralign-ui/runs/6c82c2832a4c/evidence.json
            planner heuristic · events 10 · tools executed: erp_post_invoice
            tools replayed: invoice_find_latest · predicates 8/8 passed
```

The second click — same task, same scratch, nothing runs again:

```
$ POST /api/run   -> 202   {phase: running, clicks: 2}

$ GET /api/state
  phase done | banner: pass 8/8   replayed=2   | erp rows: 1   (row id still 1)
  ↻ s1  invoice_find_latest    CX-2024-0912  $4,820.00 USD  due 2024-10-12
  ↻ s2  erp_post_invoice       ERP row #1 created
  evidence  /tmp/centralign-ui/runs/6d8ab17d18d8/evidence.json
            events 8 · tools executed: none · tools replayed: erp_post_invoice, invoice_find_latest
            predicates 8/8 passed
```

The ERP row itself, read straight out of `/api/state`:

```
count 1
{"id": 1, "idempotency_key": "inv-8e41e8ea926c4efb4a4836cb", "vendor": "ACME SUPPLY CO.",
 "company": "Company X", "invoice_number": "CX-2024-0912", "amount": "4820.00",
 "currency": "USD", "due_date": "2024-10-12", "source_file": "INV-X-2024-0912-acme.pdf"}
```

### The other two cards, clicked after the take

Not part of the 83s — this is what an evaluator gets when they click the second and third card, and
it is why the page is not a one-trick demo. Both were run cold (the scratch is wiped on a card
switch) with no approval and no ERP write; captured the same way, over HTTP:

```
$ POST /api/scenario {"id": "inbox"}    -> 200   task: list the invoice inbox in seed/invoices …
$ POST /api/run                         -> 202
$ GET /api/state
  phase done | banner: pass 9/9   replayed=0   | erp rows: 0   | pending: []
  plan_source: heuristic   plan: s1:files_list -> s2:invoice_parse -> s3:invoice_parse
  ✓ s1  files_list      3 files in seed/invoices · INV-X-2024-0703-acme.pdf, INV-X-2024-0912-acme.pdf, INV-Y-2024-0805-other.txt
  ✓ s2  invoice_parse   CX-2024-0703  $480.00 USD  due 2024-08-02  (ACME SUPPLY CO.)
  ✓ s3  invoice_parse   GY-2024-0805  $9,999.99 USD  due 2024-09-04  (GLOBEX TRADING)
  evidence  …/runs/600ef42f9e97/evidence.json · heuristic · events 12
            tools executed: files_list, invoice_parse · tools replayed: none · 9/9 passed
  approval queue: the file does not exist — nothing was ever queued

$ POST /api/scenario {"id": "check"}    -> 200   task: find the latest invoice for Company X and report its vendor, amount and due date
$ POST /api/run                         -> 202
$ GET /api/state
  phase done | banner: pass 7/7   replayed=0   | erp rows: 0   | pending: []
  plan_source: heuristic   plan: s1:invoice_find_latest
  ✓ s1  invoice_find_latest   CX-2024-0912  $4,820.00 USD  due 2024-10-12
  evidence  …/runs/0b3698de6cbc/evidence.json · heuristic · events 8 · tools executed: invoice_find_latest · 7/7 passed
```

`pass 9/9` and `pass 7/7` are not `pass 8/8` re-worded: the verifier emits six gates plus one
criterion per planned step, so a three-step job is graded on nine predicates and a one-step job on
seven. The read-side plans reach only `risk: read` tools, which is why no approval is queued and the
ERP still holds the one row from the first card — the second and third runs wrote nothing to it.

### What the badge says when a model was asked but could not answer

`python3 -m src.ui.app` with no key exported — the page's only mode — run end to end:

```
$ GET /api/state
  plan_source: heuristic(fallback: LlmError: no usable LLM key: set GEMINI_API_KEY or OPENAI_API_KEY in the environment)
  banner: pass 8/8   replayed=1   | erp rows: 1
THE PLAN      model fallback: LlmError: no usable LLM key: set GEMINI_API_KEY or OPENAI_API_KEY
              in the environment, deterministic planner used
```

The run still passes 8/8 on the deterministic plan, and the badge says why — it never claims a
model. With a working key the same field reads `llm:gemini/gemma-4-31b-it` and the badge reads
`llm · gemini/gemma-4-31b-it`; see `prompts/phase-12-gemini-planning/REPORT.md` for that run.

### Terminal tail

```
$ python3 -m src.security.scan
scanning 6 trees for credentials  … none
allowlisted canaries  2  (tests/, marker-checked: the line must still say why)
guards  deny unknown tool · deny evil host + suffix trick · deny /etc traversal · redactor masks a live secret

findings: 0  → safe to publish
rc=0

$ python3 -m pytest tests/ -q
163 passed, 1 skipped in 15.32s
```

The `15.31s` is one measured run on a laptop; yours will be a few tenths either side. The count
`163 passed` is the part that must not move.

### Every page bug this script used to warn about is fixed

The Evidence panel's `planner` row used to render `undefined` (Phase 11 flagged it; Phase 13 fixed
it), so the 0:37 beat carried a "don't re-take for it" note and the 0:05 page anatomy had no strip
or gallery in it. Both notes are gone from this script because there is nothing left to excuse:
`planner online` and the `THE PLAN` badge now read the run's own `plan_source`, and the strip
and the three job cards are quoted above from the same live session.

---

## RECORDING.md — the shoot

One take, 75–90s, browser + terminal, no cut-and-paste mid-take.

**Screen recording.** macOS: QuickTime → *File ▸ New Screen Recording*, drag the frame over the
window you're using, then **stop with ⌘⌃Esc** and trim to 83s in the QuickTime editor. Nothing to
install. Command-line equivalent if you'd rather not use the GUI:

```bash
# record ~95s, then trim to 83s; macOS 13+ (this machine: 27.0.1)
screencapture -v -V95 /tmp/centralign-ui.mov
```

Record a little longer than you need and trim at the end — a live `screencapture` stop is fine but
the tail is easier to cut in the editor than to re-take.

**Camera / frame.**

| beat | frame | notes |
|---|---|---|
| 0:00 open | terminal, full | nothing behind it — dark background, no editor or file manager |
| 0:05 run | browser, full, 1280×800 | cursor visible and moving deliberately |
| 0:25 approval | browser, right card pushed in | or full frame and narrate — both read |
| 0:37 post | browser, full | hold on the green banner |
| 0:49 replay | browser, full | the button must read `Run again (run 2)` |
| 1:01 checks | terminal, full | `ctrl-c` the page first |
| 1:13 close | either — hold on the green banner | it's the last thing on screen |

**Before you press record, run these once so nothing is cold on camera:**

```bash
python3 -m src.cli.main doctor                    # deps + seed; fix anything it flags
python3 -m src.ui.app --port 0                    # warm the import path + the sim ERP, then ctrl-c
python3 -m pytest tests/ -q                       # the suite will be cold on camera otherwise
```

**Browser:** 1280×800, 100% zoom, full screen (⌃⌘F) so nothing reflows mid-take. No devtools, no
second tab, no notification banners. The page polls at 500ms, so every state you narrate is on
screen within half a second of the click — don't narrate a change before it renders.

**Mic beats.** Land these on the action, not before it — read the number that is on screen rather
than finishing a sentence from memory:

| at | say |
|---|---|
| 0:00 | "no install, no API key, no internet" (as the terminal prints) |
| 0:05 | **on the click** — "Run" |
| 0:07 | "four thousand eight hundred and twenty dollars over a one-thousand-dollar limit" |
| 0:25 | **on the click** — "Approve", then "that name goes into the audit trail" |
| 0:37 | **on the banner** — "pass eight of eight" |
| 0:49 | **on the click** — "Run again", then "nothing executed, replayed equals two" |
| 1:01 | "zero findings", then "one hundred and sixty-three tests" |
| 1:13 | slow — this is the positioning, don't rush it |

**Timing.** The whole click-cycle is ~4 seconds of real time; the 83s is narration. Land the beats
on the timestamps at the top of this script. If you run long, cut the **checks** beat to 8s. Never
cut **approval** or **replay** — those two are the difference between an agent demo and an agent
you can trust. You may hard-cut between the browser block and the terminal tail; you may not cut
inside a run.

**If a beat glitches:** cut and re-take that block. Nothing here is edited afterwards.

**Upload.** Upload it unlisted (anyone with the link, not listed on your profile) — the grader
needs it, the world does not. The submitted take:
https://drive.google.com/file/d/1cgjTLso1PJflQ_-UQxXVWYsbXhDQq8hh/view?usp=sharing

**The honest caveat, if you want to say it on camera:** the page has no offline mode — it asked the
model on every run — and the badge tells you exactly what came back. Export a key before you record
and it reads `llm · gemini/gemma-4-31b-it`, the plan on screen is the model's, and the multi-key
router was proven live against Gemini (`plan: llm:gemini/gemma-4-31b-it`, `pass 8/8`). Record
without one and it reads `model fallback: … no usable LLM key …`, the deterministic planner did the
work, and you say so. Budget ~30–60s per model call when a key is exported: the page never fakes a
plan it was not given.
