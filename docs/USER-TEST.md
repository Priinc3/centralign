# USER-TEST — verify CentrAlign by hand, top to bottom

You do not need to read any code to do this. Twelve commands, each with the exact output you
should see, what to do if you see something else instead, and a box to tick. About 15 minutes.

Work in a **fresh terminal** with **no API keys exported**. If a step passes on your machine,
paste the output line into the demo video or the submission form — that is the point.

---

## 0. Before you start

### What needs an API key: nothing

| thing | key needed? | what happens without it |
|---|---|---|
| steps 1–12 below | **none** | — |
| live LLM planning (step 13, optional) | `GEMINI_API_KEY`, optionally `GEMINI_API_KEY_2`, `GEMINI_API_KEY_3`, … or `OPENAI_API_KEY` | the planner uses its deterministic offline plan (`plan: heuristic`), the run continues and still passes 8/8 — with `--llm` it also names the reason it fell back |
| step 10, the browser | `pip install playwright` (free, no key) | the browser check says `SKIP` and exits 0 |

No other API is called anywhere. There is no cloud service, no signup, no company account.
The only network the whole system touches is `127.0.0.1` on your own machine. **Never put real
company credentials into this project** — the system only ever talks to the simulated ERP it
starts itself.

### Prerequisites

- Python 3.11 or newer — check with `python3 -V`
- (optional, for the test suite and the LLM path) `python3 -m pip install -r requirements.txt`
- (optional, for step 10 only) `pip install playwright && python3 -m playwright install chromium`

Nothing else. No Docker, no database server, no internet.

### The one rule about scratch space

Every command below writes only under `/tmp`. That is deliberate: a cold run always starts from
an empty simulated ERP and an empty ledger, so what you see is the work and not a warm cache.
You are told before anything is deleted, and nothing outside `/tmp` is ever removed.

---

## Step 1 — is this machine ready?

```bash
python3 -m src.cli.main doctor
```

**Expect** (the middle rows vary with what you have installed):

```
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
sim ERP     note   not running at http://127.0.0.1:8901 — fine: the demo starts its own per run
network     ok     not needed: no API key, no internet — only 127.0.0.1 is contacted

ready: the offline demo runs (python3 -m src.cli.main demo)
```

The last line must say **ready**, and the exit code must be `0`:

```bash
python3 -m src.cli.main doctor > /dev/null; echo "exit code: $?"
```

**If you see instead**

| you see | do this |
|---|---|
| `not ready: fix the fail lines above` | read the `fail` rows; each one names the fix command |
| `python fail … need >= 3.11` | install Python 3.11+ (`brew install python@3.12`) |
| `pydantic fail — absent` | `python3 -m pip install -r requirements.txt` |
| `seed fail — none` | `python3 data/seed/make_pdfs.py` |
| `runs dir fail … not writable` | run everything from inside the cloned repo folder |
| `sim ERP note` | **this is fine**, not a problem — the demo starts its own ERP |

- [ ] step 1: `ready: the offline demo runs`, exit code 0

---

## Step 2 — the whole demo, cold, one command

This is the command an evaluator runs. It creates a simulated ERP and a ledger under
`/tmp/uat`, reads a seeded invoice, stops for a human approval, posts it, and verifies the
result against the ledger.

```bash
bash demo/run.sh /tmp/uat
```

**Expect** (your run ids and port will differ — everything else should match):

```
CentrAlign demo · scratch /tmp/uat · offline, no API key needed
seed        3 files in data/seed/invoices, newest = CX-2024-0912 $4,820.00 due 2024-10-12
fresh       /tmp/uat/sim.db  (empty ERP db)
sim ERP     http://127.0.0.1:64886  db=/tmp/uat/sim.db  (started for this run, stopped when it ends)
fresh       /tmp/uat/runs  (run root)
fresh       /tmp/uat/gate.jsonl  (approval queue)
erp rows    0
task        find latest invoice from Company X and post it to the ERP

run 1  6d7233234e44
  ✓ s1  invoice_find_latest    CX-2024-0912  $4,820.00 USD  due 2024-10-12
  ⏸ s2  erp_post_invoice       not posted — waiting for a human to approve it (queued below)

1 approval needed before this can continue:
  ✓ 6fe5f3707c7b  erp_post_invoice $4,820.00  approved by demo-operator   (erp_post_invoice requires approval)

run 2  continuing 6d7233234e44  (new run id: the ledger is append-only)
  ↻ s1  invoice_find_latest    CX-2024-0912  $4,820.00 USD  due 2024-10-12
  ✓ s2  erp_post_invoice       ERP row #1 created

verdict: pass 8/8   replayed=1   plan: heuristic   run: 8f456c9d8b29
ERP count: 1
evidence: /tmp/uat/runs/8f456c9d8b29/evidence.json
```

The four claims in that output, and what proves each:

1. `✓ s1` — it picked the **newest invoice for Company X** (`CX-2024-0912`). A newer invoice
   belonging to another company is on disk and was ignored.
2. `⏸ s2` then `1 approval needed` — **$4,820 is over the $1,000 unattended limit**, so it
   stopped and asked a human. It did not push through.
3. `run 2 … ↻ s1` — it continued under a **new run id** (the ledger is append-only, a run id
   is never rewritten) and replayed the find step instead of re-reading it.
4. `verdict: pass 8/8 … ERP count: 1` — an independent verifier graded 8 predicates **against
   the ledger rows**, and the simulated ERP gained exactly one row.

Exit code must be `0`.

**If you see instead**

| you see | do this |
|---|---|
| `refusing to use … as scratch` | pass a path under `/tmp`, exactly as above |
| `doctor says this machine is not ready` | fix step 1, then run this again |
| `verdict: blocked` | the approval was not granted — re-run the command, it approves unattended |
| `ERP count: 2` or more | something posted twice: `bash demo/run.sh /tmp/uat` **without** `--append` (see step 3) |
| `sim ERP did not come up at …` | another program owns that port — drop the number after `--port`, or pass a free `--port` |
| `no parseable Company X invoice` | `python3 data/seed/make_pdfs.py`, then run again |

- [ ] step 2: `verdict: pass 8/8`, `ERP count: 1`, exit code 0

---

## Step 3 — run it again: nothing executes twice

```bash
bash demo/run.sh /tmp/uat --append
```

**Expect**

```
erp rows    1
run 1  13aa037a11c9
  ↻ s1  invoice_find_latest    CX-2024-0912  $4,820.00 USD  due 2024-10-12
  ↻ s2  erp_post_invoice       ERP row #1 created

verdict: pass 8/8   replayed=2   plan: heuristic   run: 13aa037a11c9
ERP count: 1  (unchanged: nothing was double-posted)
```

`kept …` lines at the top are expected: `--append` is what tells the demo to keep the scratch.
`replayed=2` and "unchanged" are the claim to record: **a pass served from the ledger is a
different claim from a pass that executed**, and the CLI tells you which one you got without
you opening anything.

**If you see instead**: `replayed=0` means the scratch was wiped (you forgot `--append`);
`ERP count: 2` means the ERP db was reset while the ledger was kept — go back to step 2.

- [ ] step 3: `replayed=2` and `ERP count: 1  (unchanged: nothing was double-posted)`

---

## Step 4 — an empty request is refused, not faked

```bash
python3 -m src.cli.main run --task ""
echo "exit code: $?"
```

**Expect**

```
verdict: blocked / No task given   replayed=0   plan: heuristic   run: 8462b7539804
  ✗ non_empty_goal: No task given
  ✗ plan_has_steps: the plan contains at least one dispatchable step
```

Exit code `1` — a refusal is a failure of the request, correctly reported. Nothing was posted.

**If you see instead**: `verdict: pass` here would be the serious bug. Stop and report it.
(The run lands under `/tmp/centralign-demo/runs`, not the repo, because an empty ask has
nothing to audit.)

- [ ] step 4: `blocked / No task given`, exit code 1, nothing posted

---

## Step 5 — when the ERP is down, it fails loudly instead of pretending

Point the run at a port where nothing is listening. This is the most important negative test in
the whole system: a failed side effect must never read as a success.

```bash
ERP_URL=http://127.0.0.1:9 python3 -m src.cli.main run \
  --task "find latest invoice from Company X and post it to the ERP" \
  --runs /tmp/uat-dead/runs --queue /tmp/uat-dead/gate.jsonl --approve alice
echo "exit code: $?"
```

**Expect** — each failing attempt is its own ledger row, so you see the same line three times
(retry with backoff), then one replan sweep, then the honest verdict:

```
  ✗ s2  erp_post_invoice       ERP unreachable at http://127.0.0.1:9/invoices: <urlopen error [Errno 61] Connection refused>
  … (three attempts, then one replan sweep: six identical lines in total) …

verdict: fail 6/8   replayed=1   plan: replan:heuristic   run: 218edfd97ea0
  ✗ every_step_resolved: s2:ERP unreachable at http://127.0.0.1:9/invoices: …
```

Exit code `1`. Note what did **not** happen: no `ERP row #1 created`, no `pass`, no invented
success. `plan: replan:heuristic` shows the retry budget was spent and one replan was attempted
before giving up.

**If you see instead**: `verdict: pass` with a connection error anywhere in the output is a
critical bug — the verifier accepted an unproven claim. Stop and report it.

- [ ] step 5: `verdict: fail 6/8`, exit code 1, no success claimed

---

## Step 6 — resume: continue a stopped run without redoing it

```bash
# a fresh run that stops at the approval gate
ERP_URL=http://127.0.0.1:9 python3 -m src.cli.main run \
  --task "find latest invoice from Company X and post it to the ERP" \
  --runs /tmp/uat-b/runs --queue /tmp/uat-b/gate.jsonl
ls /tmp/uat-b/runs                      # the run id is the directory name

python3 -m src.reliability.checkpoint --runs /tmp/uat-b/runs --resume <run_id_from_above>
```

**Expect**

```
resumed <run_id> -> run <new_run_id> [failed] verdict=fail
inherited: {'s1': 'succeeded', 's2': 'skipped'}
steps:     ['cached', 'failed']
```

Two things to check: the run id is **new** (`<new_run_id>`), and step `s1` came back `cached`,
not re-executed. Interrupting any run is safe — the ledger knows how far it got.

**If you see instead**: `KeyError: unknown run_id` means the id was wrong (copy it from
`ls`); the ledger is append-only, so an id is never reused.

- [ ] step 6: `steps: ['cached', …]` and a **new** run id

---

## Step 7 — the human approval drill (a real person in the audit trail)

Start a simulated ERP in its own terminal, so you can drive the run by hand:

```bash
# terminal 1 — leave running
python3 sim_app/server.py --port 8912 --db /tmp/uat-c/sim.db

# terminal 2
export ERP_URL=http://127.0.0.1:8912
python3 -m src.cli.main run \
  --task "find latest invoice from Company X and post it to the ERP" \
  --runs /tmp/uat-c/runs --queue /tmp/uat-c/gate.jsonl

# the queue a human sees
python3 -m src.reliability.hitl --pending --queue /tmp/uat-c/gate.jsonl

# approve it as yourself (this is the whole approval)
python3 -m src.reliability.hitl --approve <request_id> --approver alice --queue /tmp/uat-c/gate.jsonl

# now let it continue
python3 -m src.reliability.checkpoint --runs /tmp/uat-c/runs --resume <run_id>
curl -s http://127.0.0.1:8912/invoices
```

**Expect**

```
9292a537493d  erp_post_invoice  amount=4820.0  erp_post_invoice requires approval
9292a537493d granted by alice
resumed <run_id> -> run <new_run_id> [completed] verdict=pass
inherited: {'s1': 'succeeded', 's2': 'skipped'}
steps:     ['cached', 'succeeded']
{"count": 1, "invoices": [{"id": 1, … "invoice_number": "CX-2024-0912", "amount": "4820.00", …}]}
```

Exactly **one** row, and the approver's name (`alice`) is in `gate.jsonl`. Try the wrong thing
on purpose — a decision cannot be flipped once made:

```bash
python3 -m src.reliability.hitl --approve 9292a537493d --approver mallory --queue /tmp/uat-c/gate.jsonl
# refused: request 9292a537493d is already 'closed'          (exit code 2)

python3 -m src.reliability.hitl --deny <a_pending_id> --approver mallory --reason "wrong vendor" --queue /tmp/uat-c/gate.jsonl
# <a_pending_id> denied by mallory
```

A denial is recorded, not shrugged off — and that call stays denied until someone raises a new
request. **If you see instead**: `count: 2` means the post ran twice; `granted by alice` with no
name recorded means the audit trail is broken.

- [ ] step 7: `granted by alice` → `verdict=pass` → `count: 1`, and re-approving is `refused`

---

## Step 8 — nothing in the tree looks like a credential

```bash
python3 -m src.security.scan
echo "exit code: $?"
```

**Expect**

```
scanning 6 trees for credentials  … none
allowlisted canaries  2  (tests/, marker-checked: the line must still say why)
guards  deny unknown tool · deny evil host + suffix trick · deny /etc traversal · redactor masks a live secret

findings: 0  → safe to publish
```

Exit code `0`. This is not only a grep: it calls the real guards and refuses to pass if the
allowlist, the path sandbox, the policy gate or the redactor has stopped denying — and it
includes a **positive control**, so "it found nothing" cannot mean "it matches nothing".

**If you see instead**: `findings: 1+` means do not submit. Each line names the file and the
pattern; anything that looks like a real key must be deleted, not committed.

- [ ] step 8: `findings: 0  → safe to publish`, exit code 0

---

## Step 9 — the test suite

```bash
python3 -m pip install -r requirements.txt   # once
python3 -m pytest tests/ -q
```

**Expect**

```
163 passed, 1 skipped in 15.32s
```

It takes about 16 seconds and makes **no network calls and needs no key**. The one skip is the
browser test, which needs playwright (step 10). The count is the part that must match; the seconds
are one measured run on a laptop and move a second or two either way. On a machine without the
pinned `requirements.txt` you may instead see the collection error about missing `openai`/`pydantic` —
run the pip line above.

- [ ] step 9: `163 passed, 1 skipped`, no key exported

---

## Step 10 — a real browser, on a real page

```bash
python3 scripts/browser_check.py
echo "exit code: $?"
```

**Expect, with playwright installed**

```
CentrAlign browser check · localhost only · scratch /tmp/centralign-browser
  ✓ allowlist              evil.com, the suffix trick and file:// refused, no browser launched

sim ERP   http://127.0.0.1:64853  db=/tmp/centralign-browser/sim.db  (started for this check, stopped when it ends)
  ✓ portal loads           HTTP 200, title 'Acme portal — inbox'
  ✓ 3 invoices listed      2024-0703-acme.pdf — 993 bytes, 2024-0912-acme.pdf — 1156 bytes, 2024-0805-other.txt — 201 bytes
  ✓ screenshot             /tmp/centralign-browser/portal.png

PASS: the portal rendered in a real browser, the allowlist refused evil.com without launching one, and the screenshot is on disk.
```

Open the screenshot and look at it — it is a genuine headless-chromium render of the invoice
portal listing the three seeded files.

**Expect, without playwright** — same exit code `0`, different words, because a missing
optional dependency is not a defect:

```
CentrAlign browser check · localhost only · scratch /tmp/centralign-browser
  ✓ allowlist              evil.com, the suffix trick and file:// refused, no browser launched

SKIP: playwright is not installed, so there is no browser to drive. …
      to run this check anyway:  pip install playwright && python3 -m playwright install chromium
```

To install it: `pip install playwright && python3 -m playwright install chromium` (~150 MB, once).
The check itself then takes under 2 seconds.

**If you see instead**

| you see | do this |
|---|---|
| `SKIP: playwright is not installed` | install it as shown, then re-run |
| `chromium could not drive the portal: … Executable doesn't exist` | `python3 -m playwright install chromium` |
| `the sim ERP did not come up` | `python3 sim_app/server.py --port 8911 --db /tmp/x.db` in another terminal, then re-run |
| `expected the 3 seeded invoices, portal lists 4` | someone added a seed file: `python3 data/seed/make_pdfs.py` restores the shipped three |

- [ ] step 10: `PASS` (or a clean `SKIP` with exit code 0), and the screenshot opened and looked at

---

## Step 11 — read the evidence yourself

Every run leaves a bundle. Read one claim end to end:

```bash
python3 - <<'PY'
import json, pathlib
run = max((p for p in pathlib.Path("/tmp/uat/runs").iterdir() if p.is_dir()),
          key=lambda p: p.stat().st_mtime)
b = json.loads((run / "evidence.json").read_text())
print("run      ", b["run"]["run_id"], b["run"]["status"], "| plan:", b["run"]["plan_source"])
print("executed ", b["totals"]["tools_actually_executed"])
print("replayed ", b["totals"]["tools_replayed"])
print("steps    ", [(s["step_id"], s["tool"], s["status"]) for s in b["steps"]])
for p in b["verdict"]["predicates"]:
    print("   ", "PASS" if p["passed"] else "FAIL", p["name"])
print("events   ", len(b["events"]), "in events.jsonl; checkpoint.json holds the counters")
PY
```

**Expect** — this reads the `--append` run from step 3, where nothing executed:

```
run       13aa037a11c9 completed | plan: heuristic
executed  []
replayed  ['erp_post_invoice', 'invoice_find_latest']
steps     [('s1', 'invoice_find_latest', 'cached'), ('s2', 'erp_post_invoice', 'cached')]
    PASS non_empty_goal
    PASS plan_has_steps
    PASS every_step_resolved
    PASS no_silent_skips
    PASS each_success_has_evidence
    PASS audit_trail_complete
    PASS criterion:s1
    PASS criterion:s2
events    8 in events.jsonl; checkpoint.json holds the counters
```

Three claims to make out loud:

1. `executed []` with `replayed` holding both tools — on an `--append` run nothing executed,
   and the bundle says so rather than implying a fresh post. On the cold run of step 2 the same
   snippet prints `executed ['erp_post_invoice']` and `replayed ['invoice_find_latest']`.
2. The eight predicates are re-derived **from the ledger rows**, not from what the executor
   claimed. The verifier never reads the executor's conclusion.
3. Each run directory holds `evidence.json`, `events.jsonl` and `state.json`. Anything that did
   not run says so in the bundle — no silent mock autonomy.

Re-run step 2 on the scratch and diff `events.jsonl` between the two runs: the second run has no
`erp_post_invoice` success event, because nothing was posted.

- [ ] step 11: 8 `PASS` predicates read out of the bundle, and the `tools_replayed` line matches the run

---

## Step 12 — record the demo

Beat sheet, timings and the exact commands: **`demo/video-script.md`** (75 seconds, one take).

Before you press record:

```bash
rm -rf /tmp/vid
bash demo/run.sh /tmp/vid            # the cold run you will record
bash demo/run.sh /tmp/vid --append   # the replay beat
python3 -m src.security.scan         # the "safe to publish" beat
python3 -m pytest tests/ -q          # the test beat
```

Use a window about 110×32 so nothing wraps. If a beat glitches, cut and re-take — nothing in
the demo is interactive, and `doctor` failing on camera is a good 10 seconds.

- [ ] step 12: video recorded, and its beats match the output you saw in steps 2–9

---

## Step 13 (OPTIONAL) — the live LLM path, with a key

**Needs at least one key. Skip this step entirely if you have none** — steps 1–12 already proved
everything the system claims *except* live model planning, which only a key can show.

Get a key at <https://aistudio.google.com/apikey> (free tier, no card). Then export it **in your
shell only** — never write it into the repo, never commit it, never paste it into a file:

```bash
export GEMINI_API_KEY='…'                 # one key
export GEMINI_API_KEY_2='…'               # optional: a second key for rotation
export GEMINI_MODEL='gemini-2.5-flash'    # optional: the default is gemma-4-31b-it, which is
                                          # much slower — see the timing note before you start
bash demo/run.sh /tmp/llm --llm
```

**This step asks a real model, not a stub.** With a key present the planner sends the tool manifest
to the endpoint, the endpoint returns a tool call, and the run executes the model's plan: it chooses
the tools, their order, the dependency between them and the success criteria.

**Expect** the same demo, with the plan source naming the provider *and the model that answered*:

```
verdict: pass 8/8   replayed=1   plan: llm:gemini/gemma-4-31b-it   run: <run_id>
ERP count: 1
```

`<run_id>` is random per run, as is everything else in the transcript. `plan: llm:<provider>/<model>`
is read back off the router after the call — it is evidence, not a label we printed ourselves. Open
the page instead (`python3 -m src.ui.app --port 0` — it has no offline mode, it asks the model on
every run) and the badge reads `llm · gemini/gemma-4-31b-it`, or names the reason it fell back.

**Timing — read this before you start the clock.** The default Gemini model is `gemma-4-31b-it`
and it is slow: a ~1.3k-token manifest prompt in, **~30–60 s per call** at `temperature: 0`. The
demo's second run re-plans on the resume, so budget a couple of minutes for the cycle, not seconds.
Set `GEMINI_MODEL=gemini-2.5-flash` for the same plan from the same schema several times faster —
worth doing if you are recording anything.

The model is never asked to know the future: the posting step names its values as
`{{s1.latest.amount}}` / `{{s1.latest.due_date}}` and the executor resolves them out of the invoice
the read step actually found. The ERP row is therefore the seeded invoice byte for byte
(`ACME SUPPLY CO. | CX-2024-0912 | 4820.00 | USD | 2024-10-12`). Nothing in that row was written by
a model.

Keys are read in numeric order (`GEMINI_API_KEY`, then `_2`, `_3`, …) and used round-robin, so
N keys raise the rate-limit ceiling N-fold. A key that answers `429` or `5xx` is put into a
short cooldown and the next key serves the request; a bad key is skipped the same way. **No key
ever reaches a log, an event, or an error message** — the router replaces every key it holds
with `[REDACTED]` before anything is written.

Three honest caveats, all measured on a real key:

1. **It degrades, it does not break.** No key, an exhausted free-tier quota (`429`), a refused key
   (`400`), or an answer that is not a valid plan → the run prints
   `plan: heuristic(fallback: <reason>)` and completes with the same verified verdict. Degradation
   is the designed behaviour, not a silent pass, and the reason is always on the line.
2. **Gemini needed one schema change to accept this repo's plan.** Its OpenAI-compatible endpoint
   rejected the strict schema outright — `function_call_filter: MALFORMED_FUNCTION_CALL`,
   `completion_tokens: 0`, with and without `strict: true` — and the one key that had to go was
   `title`, the field pydantic puts on every model. The router now sends Gemini a profile with only
   `title` removed, `strict: true` still set; an OpenAI endpoint receives the tool byte-identical.
   If you ever see the fallback again, read the reason before assuming the model refused the task:
   a free-tier `429` looks the same from the outside.
3. **The compat endpoint 500s intermittently** — roughly one request in three on `gemma-4-31b-it`.
   With a single key the router retries in place (the same request, immediately), which is why
   repeated `--llm` runs are stable; with two or more keys it fails over instead.

Verify the rotation and the schema profile without any key at all — both are fully offline:

```bash
python3 -m pytest tests/test_llm_router_keys.py -q         # 12 passed — rotation, cooldowns, redaction
python3 -m pytest tests/test_llm_gemini_planning.py -q    # 16 passed — the google profile, temp: 0,
                                                          # plan_source, fallback, {{s1.latest.*}} refs
```

Also still open, so you are not surprised by it: `python3 -m src.cli.main run --task …` (without
`demo`) only attempts the LLM path when `OPENAI_API_KEY` is set — that check predates multi-key
routing (`prompts/phase-05-demo-ux/FIX-2.md`, not yet applied; `src/cli/main.py:508`). Use
`demo … --llm` or the page to exercise Gemini keys.

- [ ] step 13 (optional): `plan: llm:<provider>/<model>` with a key, or the documented fallback
      message with its reason — and the ERP row still matches the seeded invoice

---

## Before you submit

- [ ] **Video URL** pasted into the submission form and reachable (unlisted is fine, not
      private) — 60–90s, recorded from `demo/video-script.md`
- [ ] **GitHub / source URL** pasted in, repository public or invite-only but reachable, and
      the code on the default branch is what you tested
- [ ] **`bash demo/run.sh`** passes on a machine that is not yours (ask a colleague, or a
      fresh clone in a new folder) — this is the single command an evaluator will run
- [ ] **No key, no `.env`, no real company data** in the repository — step 8 proves it
- [ ] **README quickstart output** matches what you get today (`bash demo/run.sh`)
- [ ] Any deviation you hit along the way is written down, with the command that triggered it —
      a known quirk you can explain is worth more than a surprise an evaluator finds

## Known quirks (measured, not hypothetical)

| what you see | why | what it means |
|---|---|---|
| `plan: heuristic(fallback: …)` with `--llm` | no usable key (none exported, a `400`-refused key, or a free-tier `429`) — earlier builds also hit Gemini's `MALFORMED_FUNCTION_CALL` on the strict schema, which is now fixed by the title-free google profile (step 13) | the run still passes; read the reason in the message: `no usable LLM key` means this machine, `PlannerError` means the endpoint refused the schema |
| `--llm` is slow, not broken | the default Gemini model `gemma-4-31b-it` takes ~30–60 s per call at `temperature: 0`, and resuming re-plans | budget a couple of minutes for the two runs, or set `GEMINI_MODEL=gemini-2.5-flash` |
| `seed … newest = CX-2024-0912`, and the seeded `.txt` invoice never appears | the offline planner's find step globs `*.pdf` | stated limit in the README; `invoice_find_latest` parses the `.txt` fine when asked directly |
| `runs dir ok …/centralign/runs` created by doctor | doctor checks that a run directory is writable | harmless; the demo uses `/tmp` |
| `sim ERP note … not running at http://127.0.0.1:8901` | nothing is listening on the conventional port | by design; the demo starts its own on a free port |