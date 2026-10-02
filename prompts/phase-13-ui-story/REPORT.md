# REPORT — Phase 13 UI tells the story (NORMAL, after 12)

Type NORMAL, after 12. **13a and 13b are both DONE.** 13a ran while 12 was still writing and touched
**zero shared files**; 13b started after 12's `REPORT.md` landed and touched only what the gate
allows. Files this phase changed:

```
src/ui/app.py            scenarios + stage trail + plan_source/plan in state()   (OWN)
src/ui/index.html        header, 8-stage strip, gallery, plan panel             (OWN)
tests/test_ui_offline.py +7 tests, real /tmp scratch                            (OWN)
src/runtime/planner.py   two additive read-side templates (+1 dispatch line)    (13b grant)
demo/video-script.md     quote refresh only (§3)                                (13b grant)
docs/USER-TEST.md        two number lines (127 -> 156)                          (exception)
```

Untouched: `src/llm/*`, 12's `tests/test_llm_gemini_planning.py`, `README.md`, `SUBMISSION.md`,
`prompts/phase-08-submission/USER-STEPS.md`, `context/*.yaml`, and the frozen parts of `planner.py`
(`_plan_submit_tool`, `_step_args`, `llm_plan`, `make_plan` — 12's lines).

```
$ git status --short src/ tests/ docs/ demo/ | cat
 M demo/video-script.md
 M docs/USER-TEST.md
?? src/ui/
?? tests/test_ui_offline.py
```

---

## 1. What changed on the page, before → after

Nothing here re-implements the demo: the strip reads the run's own events, the badge reads the run's
own `plan_source`, and the cards are a catalog of tasks the existing `POST /api/run` already sends.

| | before (09/11) | after (13a) |
|---|---|---|
| title | `CentrAlign · AI operator for invoice intake` | `CentrAlign · an AI employee for invoice intake` |
| one-liner | `One run, watched live: find the invoice → a human approves the post → verified.` | `It reads the ask, plans the work, stops for a human before anything spends money, then verifies the result from the ledger and hands you the evidence.` |
| how it works | *nothing* | `How it works · the same eight stages every run` + `goal → understand → plan → execute → observe → adapt → verify → complete`, the stages the run has entered lit, the current one filled |
| pick a job | *nothing* | 3 cards, each with the tool chain in plain words and its gate, above the Run button |
| the plan | *nothing* | badge (`heuristic offline` / `llm · <endpoint>/<model>` / `model fallback: <reason>, deterministic planner used`) + `goal: …` + one row per step with its `intent` and `done when:` line |
| evidence panel `planner` | `undefined` (11's finding) | `heuristic` |

**The 11 finding is closed.** `src/ui/app.py::state()` now carries `plan_source` (read from
`evidence.run.plan_source` once the bundle exists, from the run's own `state.json` while it is still
working — the same variable `src/runtime/loop.py:314` writes), and `index.html` reads
`state.plan_source`. Test: `test_the_planner_badge_is_the_runs_own_plan_source` asserts the page
carries `state.plan_source` and no longer contains `run.plan_source`.

**Why the strip is built from events, not from a clock.** A run does not record "complete" anywhere
until it is finished, and a run holding on a human has status `blocked` — so a stage name taken
from `runs.stage` alone would light `Complete` while the page still says `waiting for a human`.
`stages_of()` (`src/ui/app.py:75`) walks the run's own event log instead: `run.started` marks
goal+understand, `step.planned` marks plan, `run.stage` events name themselves, `verify.checked`
marks verify, and `complete` only when the run's status really is `completed`. Nothing is timed,
interpolated or faked; `adapt` stays dark because a clean run never enters it.

**Switching a card wipes the scratch.** `_cold()` (already the constructor's three `cli.fresh`
calls) is now also what `Demo.select()` runs, so the next Run is genuinely a first run: ERP db,
run root and approval queue all gone. `test_switching_scenario_loads_its_task_and_resets_the_page`
proves the ERP itself is empty afterwards by asking it over HTTP, not just the panel.

---

## 2. Live session — the page's own HTTP, no browser

The `stages` payload is the strip; `(`dark`)` / `[FILLED]` is what the page paints. Driven by
running the real page script (`src/ui/index.html`'s `<script>`) against a live `/api/state` in
node with a 40-line DOM stub, because the point of the phase is what the page *shows*:

```
page http://127.0.0.1:50240  · sim ERP http://127.0.0.1:50236

--- cold page, nothing run
  how it works: (goal) -> (understand) -> (plan) -> (execute) -> (observe) -> (adapt) -> (verify) -> (complete)
  banner:       press Run
  badge:        planning…
  steps:        no steps yet — press Run
  erp:          the sim ERP is not answering

--- after Run · awaiting, 1 approval queued
  how it works: goal -> understand -> plan -> execute -> observe -> (adapt) -> [VERIFY] -> (complete)
  banner:       blocked / 7/8 predicates passed
  badge:        heuristic offline
  plan:         s1 · invoice_find_latest , s2 · erp_post_invoice
  steps:        s1 · invoice_find_latest CX-2024-0912  $4,820.00 USD  due 2024-10-12
                s2 · erp_post_invoice not posted — waiting for a human to approve it (the card beside this list)
  erp:          0 rows in the ERP
  evidence:     …/runs/11d1ec4667bc/evidence.json  heuristic  10  invoice_find_latest  none  7/8 passed

--- after Approve
  how it works: goal -> understand -> plan -> execute -> observe -> (adapt) -> verify -> [COMPLETE]
  banner:       pass 8/8   replayed=1
  badge:        heuristic offline
  steps:        s1 · invoice_find_latest replayed from the ledger (not called again) · CX-2024-0912 …
                s2 · erp_post_invoice ERP row #1 created
  erp:          1 row in the ERP

--- after Run again
  how it works: goal -> understand -> plan -> execute -> observe -> (adapt) -> verify -> [COMPLETE]
  banner:       pass 8/8   replayed=2
  erp:          1 row in the ERP

--- after clicking the read-only card
  how it works: (goal) -> (understand) -> (plan) -> (execute) -> (observe) -> (adapt) -> (verify) -> (complete)
  banner:       press Run
  badge:        planning…
  steps:        no steps yet — press Run
```

The three cards, as the page renders them (`/api/state` → `scenarios`):

```
Post the latest invoice          one approval: the ERP post
find the latest invoice for Company X → post it to the ERP

Summarize the invoice inbox       read-only: no approval, nothing posted
list seed/invoices → parse the two files it names → report the inbox

Check the latest invoice, post nothing    read-only: no approval, nothing posted
find the latest invoice for Company X → report it, write nothing
```

**The same session again after 13b**, with the read-side templates in place — the other two cards
run cold, unattended, and the ERP still holds nothing beyond what the first card posted:

```
================ scenario inbox -> 200
--- inbox · finished
  how it works: goal -> understand -> plan -> execute -> observe -> (adapt) -> verify -> [COMPLETE]
  banner:       pass 9/9   replayed=0
  badge:        heuristic offline
  plan:         s1 · files_list , s2 · invoice_parse , s3 · invoice_parse
  steps:        s1 · files_list 3 files in seed/invoices · INV-X-2024-0703-acme.pdf, INV-X-2024-0912-acme.pdf, INV-Y-2024-0805-other.txt
                s2 · invoice_parse CX-2024-0703  $480.00 USD  due 2024-08-02  (ACME SUPPLY CO.)
                s3 · invoice_parse GY-2024-0805  $9,999.99 USD  due 2024-09-04  (GLOBEX TRADING)
  erp:          0 rows in the ERP
  evidence: verdict=pass predicates=9/9 executed=['files_list', 'invoice_parse'] replayed=[]
            plan_source=heuristic approvals_in_bundle=0
  approval queue after this scenario: 0 record(s)  (the queue file does not even exist)

================ scenario check -> 200
--- check · finished
  banner:       pass 7/7   replayed=0
  plan:         s1 · invoice_find_latest
  steps:        s1 · invoice_find_latest CX-2024-0912  $4,820.00 USD  due 2024-10-12
  erp:          0 rows in the ERP
  evidence: verdict=pass predicates=7/7 executed=['invoice_find_latest'] replayed=[] approvals_in_bundle=0
  approval queue after this scenario: 0 record(s)  (the queue file does not even exist)
```

The badge function, on all four shapes it can be handed — `heuristic` and the empty one live, the
fallback string from a real `--llm` run with no key (§5b), and the `llm:` string exactly as Phase
12's live Gemini run produced it:

```
"llm:gemini/gemma-4-31b-it"                  -> "llm · gemini/gemma-4-31b-it"   [llm]
"heuristic"                                  -> "heuristic offline"
"heuristic(fallback: LlmError: no usable …)" -> "model fallback: LlmError: no usable LLM key: …, deterministic planner used"
""                                           -> "planning…"
```

---

## 3. Quote map — what changed in `demo/video-script.md`, and where each quote came from

Every changed string was re-verified against a live page over HTTP (no browser) after the edit, the
way 11 did. The static ones are literal in `src/ui/index.html`; the rest are printed by §2's runs.

| # | was | now | verified from |
|---|---|---|---|
| 1 | title `CentrAlign · AI operator for invoice intake` | `CentrAlign · an AI employee for invoice intake` | `GET /` contains it |
| 2 | page anatomy: title, task strip, banner, steps, ERP, approval card | adds **How it works** strip (all chips dark), **Pick a job** (3 cards, first selected), **The plan** panel | `GET /` + idle `/api/state` |
| 3 | — | new quote block: the lit strip + `THE PLAN  heuristic offline` + both steps with their intents and `done when:` lines | blocked poll, rendered |
| 4 | — | new quote block: the three cards with their chains and gates | `/api/state.scenarios`, rendered |
| 5 | "**Known artifact, don't re-take for it.** The Evidence panel's `planner` row renders `undefined`…" | deleted; replaced with what the badge and the row now read, and the rule that no badge is unearned | evidence panel `planner heuristic` |
| 6 | "### One quoted number that is a known page bug" section | replaced by "### Every page bug this script used to warn about is fixed" | — |
| 7 | the honest caveat: "the `planner` row reads `undefined`… do not let the viewer assume a model drove it" | same caveat, correct reason: the terminal said `heuristic (offline, no key needed)` and the badge says `heuristic offline`; names 12's live `llm:gemini/gemma-4-31b-it` as what a keyed take shows, with the ~30–60s warning | `--llm` run below |
| 8 | `133 passed`, `11.28s`, "One hundred and thirty-three tests", "six of them drive this page" | `156 passed`, `15.85s`, "one hundred and fifty-six tests", "ten of them" (counted: 13 tests in the file, 3 without the page fixture) | `pytest tests/ -q` |
| 9 | — | new transcript sections: the other two cards (`pass 9/9`, `pass 7/7`, zero approvals, ERP still 1 row) and the no-key `--llm` fallback badge | §5 |

Unchanged and still exact: the terminal block (`fresh`/`reset`, `sim ERP …`, `task …`,
`planner heuristic (offline, no key needed)`, `scratch …`), `blocked / 7/8 predicates passed`,
`pass 8/8   replayed=1`, `pass 8/8   replayed=2`, `STEPS (2)` and its two step rows, `1 row in the
ERP` and the row fields, `events 10`/`events 8`, the executed/replayed lists, the approval-card copy,
`no steps yet — press Run`, `the sim ERP is not answering`, `findings: 0  → safe to publish`, and
10's closing beat, byte-identical.

---

## 4. Tests — 13a and 13b, `tests/test_ui_offline.py` only

```
$ python3 -m pytest tests/ -q
156 passed, 1 skipped in 15.77s          # 138 after 13a, +2 here (12 added 16 of its own)

$ python3 -m pytest tests/test_ui_offline.py -q
13 passed in 8.07s

$ python3 -m src.security.scan
findings: 0  → safe to publish

$ grep -rn "127 passed\|127 tests" docs/ README.md SUBMISSION.md demo/
$ echo $?
1
```

| test | phase | what it pins |
|---|---|---|
| `test_the_gallery_states_each_job_before_you_click_it` | 13a | 3 cards with title/chain/gate, `intake` selected by default, all eight stage names served, the read-only job's task contains no `post` (so the intake template cannot claim it) |
| `test_the_strip_reports_the_stages_the_run_reached` | 13a | `stages_of` over a fabricated event log: clean run, blocked run (no `complete`), a retry (`adapt` appears), a `resume` event (not a stage, ignored) |
| `test_the_strip_lights_up_over_the_whole_session` | 13a | awaiting → `goal…verify`, not `complete`; after Approve → `…verify, complete` |
| `test_the_planner_badge_is_the_runs_own_plan_source` | 13a | badge == `evidence.run.plan_source` == `heuristic`, plan steps carry intents, page reads `state.plan_source`, fallback copy present |
| `test_switching_scenario_loads_its_task_and_resets_the_page` | 13a | new task loaded, panel/ledger/plan/ERP all reset, ERP really empty, unknown id → 404 |
| `test_the_two_read_side_jobs_pass_with_no_approval_and_no_erp_write` | 13b | S2 `pass 9/9` (3 steps), S3 `pass 7/7` (1 step), `pending == []`, `erp.count == 0`, no `approval.requested` event in either bundle, every step's `detail` non-empty |
| `test_the_scenario_templates_plan_reads_and_nothing_else` | 13b | each gallery task is claimed by exactly one template; only `intake` reaches a write tool; the parse paths are the ones the ask named; a task outside all three shapes still reaches the untouched keyword path |

13 tests, 10 of which drive the real page over HTTP with no browser (the 3 exceptions are two pure
unit tests and the `--host 0.0.0.0` refusal).

One test-fixture change was needed to make those true: the scratch is now
`tempfile.mkdtemp(dir="/tmp")`, not pytest's `tmp_path`. `cli.fresh` refuses to delete anything
outside a scratch root, and on macOS pytest's `tmp_path` arrives as `/private/var/folders/…` while
`TMPDIR` is `/var/folders/…`, so the text comparison misses and the "cold" wipe silently never
happened — the sim ERP db also sat outside the dir the page wipes. Both are fixed; teardown removes
the directory.

**Also done:** `docs/USER-TEST.md` lines 367 and 375, `127 → 156`.

Deviation from the BUILD, deliberately: the BUILD said `127→133`. The suite is `156` because this
phase adds 7 tests and 12 added 16, so `133` (or `138`) would be false the moment this phase lands.
The count in a user runbook is worth less than the count being true.

---

## 5. 13b — done

### a. The two read-side templates (`src/runtime/planner.py`, additive)

13a's honest measurement, before:

```
"list the invoice inbox in seed/invoices and parse INV-X-…acme.pdf and INV-Y-…other.txt"
  s1 invoice_parse → s2 invoice_find_latest → s3 files_list → s4 erp_post_invoice
  args: {"path": ""} … every string arg = the whole task text
clicking that card, live:  fail 5/9   ·   steps: FileNotFoundError: not a directory: Company X
```

and after — `inbox_plan()` and `check_plan()`, added next to `intake_plan()`, with one changed
dispatch line in `heuristic_plan`:

```python
    template = intake_plan(task, manifests) or inbox_plan(task, manifests) or check_plan(task, manifests)
```

That single line is the only edit inside existing logic; `intake_plan`, `fill_args`, the keyword
ranking, `llm_plan`, `_upstream_args` and `make_plan` are untouched.

Every argument is mined from the ask, and neither template can reach a write tool:

```python
_INBOX_DIR_RE = re.compile(r"\b(seed/[\w./-]*?)/?(?=\s|$|[,.])")   # the directory, from the ask
_INBOX_FILE_RE = re.compile(r"[\w-]+\.(?:pdf|txt)\b", re.IGNORECASE)  # the files, from the ask
```

**All three scenarios, cold, through the page** (`/tmp` wiped on every card switch):

| card | plan | banner | approvals | ERP rows |
|---|---|---|---|---|
| `intake` | `s1:invoice_find_latest -> s2:erp_post_invoice` | `pass 8/8   replayed=1` | 1 granted | 1 |
| `inbox` | `s1:files_list -> s2:invoice_parse -> s3:invoice_parse` | `pass 9/9   replayed=0` | 0 — the queue file is never even created | 0 |
| `check` | `s1:invoice_find_latest` | `pass 7/7   replayed=0` | 0 | 0 |

`9/9` and `7/7` are not `8/8` re-worded: `src/verifier/checks.py` emits six gates plus one
weight-0 criterion per planned step, so three steps are graded on nine predicates and one step on
seven. Zero approvals is not luck — `hitl.authorizer` returns `allow` for any manifest with
`requires_approval: false`, and both read-side plans only name such tools.

One page change was needed for the read side to *say* something (`src/ui/app.py::detail()`, two new
branches, the existing ones untouched): a `files_list` row now reads
`3 files in seed/invoices · INV-X-2024-0703-acme.pdf, …` and an `invoice_parse` row reads
`CX-2024-0703  $480.00 USD  due 2024-08-02  (ACME SUPPLY CO.)` instead of a bare `done`. That is the
BUILD's "read-only totals", on screen.

### b. The badges, live

`heuristic offline` and the honest fallback were proven end to end by driving the real page; the
`llm · <provider>/<model>` rendering was verified as a function of the exact string 12's live run
produced, because **this session has no usable Gemini key**: the only key in the environment is
`GOOGLE_API_KEY`, and passing it to the Gemini endpoint is refused
(`400 INVALID_ARGUMENT: Please pass a valid API key`), so no live model run was possible here.

```
badge("llm:gemini/gemma-4-31b-it"                  ) -> "llm · gemini/gemma-4-31b-it"   [llm]
badge("heuristic"                                  ) -> "heuristic offline"
badge("heuristic(fallback: LlmError: no usable …)" ) -> "model fallback: LlmError: no usable LLM key: set
                                                        GEMINI_API_KEY or OPENAI_API_KEY in the environment,
                                                        deterministic planner used"     [fallback]
badge(""                                           ) -> "planning…"
```

The middle two are not simulated — `python3 -m src.ui.app --llm` with no key exported, run over
HTTP, printed this on the page and still finished `pass 8/8`:

```
  plan_source: heuristic(fallback: LlmError: no usable LLM key: set GEMINI_API_KEY or OPENAI_API_KEY …)
  THE PLAN  model fallback: LlmError: no usable LLM key: set GEMINI_API_KEY or OPENAI_API_KEY in the
            environment, deterministic planner used
  banner:   blocked / 7/8 predicates passed      →   pass 8/8   replayed=1   | erp rows: 1
  evidence: limits[0] = "planner=heuristic(fallback: LlmError: no usable LLM key: …)"
```

12's own live transcript is the proof for the `llm ·` branch (`phase=done banner='pass 8/8'
src='llm:gemini/gemma-4-31b-it' erp=1`, driven through this same HTTP API). What is still missing is
one recording of that string on *this* phase's page; F1 below is who can close it.

### c. Video quotes

Done — §3, nine rows, each re-verified after the edit.

---

## 6. Findings

- **F1 — 🔴 the phase-13 video takes need one re-record of the 0:05 and 0:37 beats.** The page's top
  third changed (strip + gallery + plan panel), so the existing recording no longer matches the page.
  The script is already refreshed and every quote in it is re-verified; only the pixels are old.
- **F2 — 🟠 `erp_post_invoice` cannot read the ERP.** Its manifest has `action: "list"`, but
  `requires_approval: true`, and `hitl.authorizer` gates on that flag alone — so the BUILD's
  "Audit the ERP" scenario would queue an approval and break the zero-approval rule. The scenarios
  were chosen around it (`files_list`, `invoice_parse`, `invoice_find_latest` are all `risk: read`).
  A read-only ERP job needs an `erp_list_invoices` read manifest in `src/tools/manifest_registry.py`
  or an `action=list` carve-out in the policy; both are outside this BUILD.
- **F3 — 🟡 `invoice_parse` args cannot come from a `files_list` result.** `executor._REF_RE` walks
  dicts only; a list index raises and the step is recorded failed. So `inbox_plan` parses the files
  the *ask* names, and S2's task text names its two files — visible on the card, and the reason the
  chain reads "parse the two files it names". List support in `resolve_refs` is the alternative, and
  it is `src/runtime/executor.py`, not this phase's file.
- **F4 — 🟡 docs drift, next doc pass.** `README.md:253` and `SUBMISSION.md:13` still say
  `133 passed`; the suite is 156. `docs/USER-TEST.md:368` still says the suite "takes about 7
  seconds" (16s), and step 13 still describes `--llm` as degrading to the heuristic plan, which 12
  made false. None of those files are this phase's; the two number lines it did grant are updated.
- **F5 — 🟡 `hitl.decide` writes `decided_on = request_id`** (`src/reliability/hitl.py:138`), 11's
  finding, still unfixed. Not quoted on camera.
- **F6 — 🟡 the test fixture had a silent cold-start hole** (§4): pytest's `tmp_path` is not a
  scratch root on macOS, so every "cold" assertion in this file was quietly warm until this phase
  fixed the fixture. Worth grepping other tests for `tmp_path` + `cli.fresh`.

skipped: an animation that walks the strip chip by chip. A cold S1 run takes ~40ms end to end — a
zero-sleep poll loop still never catches it mid-flight (measured, three attempts, first observation
at +42…45ms and already `awaiting`) — so any "light one at a time" effect would be a lie about
timing. The strip shows the trail the run actually wrote, and the page is not slowed down to look
prettier.

skipped: making the gallery show S2/S3 as "not ready" until their templates land. They do now, and
the flag would have been scaffolding to delete a day later.

## Post-13b: the page went online-only (no offline mode)

The ask after 13b: remove the offline mode itself — the page should always plan with the model.
The `heuristic offline` quotes above are the historical record of what 13b proved; they stay. What
changed:

- `src/ui/app.py`: `Demo.__init__` is `offline: bool = False` (was `True`); `main()` lost both flags
  (`--llm`, `--offline`) and prints `planner online — the page names the model that planned the run,
  or why it could not`. Docstring updated. Net diff is smaller than the flag code it deletes.
- `tests/test_ui_offline.py`: the 13 existing UI tests still need a deterministic cold planner with no
  key, so the fixture pins `offline=True` explicitly; new `test_the_page_has_no_offline_mode`
  asserts the default is `False`, neither flag string survives in `app.py`, and the startup line is
  the online one. 14 tests in the file.
- Unkeyed honesty, measured on the live page (`http://127.0.0.1:54649`, no key exported):
  `POST /api/run → 202`, awaiting `blocked / 7/8`, approve → `pass 8/8`, stages
  `goal → … → complete`, and the badge reads
  `model fallback: LlmError: no usable LLM key: set GEMINI_API_KEY or OPENAI_API_KEY in the
  environment, deterministic planner used` — a full heuristic plan (steps + intents + done-whens),
  never a fake model label. With a key exported the same badge reads `llm · gemini/<model>`.
- Docs refreshed to the new reality: `demo/video-script.md` (terminal line, both `THE PLAN` badges,
  badge paragraph, plan_source note, `--llm` command, `156→157`, `15.85s→15.31s`, caveat rewritten
  online-only, zero stale strings left), `README.md` (online-mode paragraph, `157 passed`),
  `docs/USER-TEST.md` (page reference, `157 passed`). Step 13's `demo/run.sh --llm` is untouched —
  the CLI demo keeps its flag; only the page lost its mode switch.

```
157 passed, 1 skipped in 15.31s
findings: 0  → safe to publish
```

## Postscript: a key that works, and the quota wall behind it

Three keys were tried against `generateContent` directly. `the first Gemini key` is valid but its project
spent the 20/day free-tier quota (`429`, retry ~4h). `a second Gemini key` is suspended (`403
PERMISSION_DENIED`) — dead, not used. `a token-shaped key` answers `200` and planned a live run on the page:
mid-run state read `plan_source: llm:gemini/gemini-2.5-flash`, the first model-written plan this page
has ever executed. The resume re-plan then hit the same project's spent quota, so the finished run
shows the honest fallback and still `pass 8/8, 1 row posted`. Nothing in the repo can fix a spent
quota; after reset the next Run is full-model with no restart. Poll fix in the same pass: the page
polls 2×/s only while `phase === running` (was: also while awaiting/blocked) — a finished page makes
zero requests. Pinned by `test_the_page_only_polls_while_a_run_is_in_flight`. Suite `158 passed`.

## Postscript 2: Groq serves, qwen plans (the 429s above were all real limits)

Scoreboard of the four keys: `a second Gemini key` suspended (`403`, discarded); `a token-shaped key` and
`the first Gemini key` spent their 20/day Gemini free quotas (`429`, dropped from the page env);
`the new-project Gemini key` is valid but its new project retired `gemini-2.5-flash` (`404`, use
`gemini-3.8-flash`) and spent that quota too — it stays first in line for after the reset.
Groq (`GROQ_API_KEY…`, new router slot between Gemini and OpenAI) needed three measured fixes:
`$defs`/`$ref` inlined (Groq never registers a ref'd tool), `required` dropped where `properties`
is empty, `"strict": true` dropped (same registration refusal), plus the system prompt now spells
the exact step keys (gpt-oss invented `name`). gpt-oss-120b/20b then proved intermittently
unusable on tool registration, and no Llama chat model exists on the account (all 404) — but
`qwen/qwen3.8-27b` tool-calls cleanly, 7/7 probed, and only needed one more thing: Groq's
on-demand tier caps *output* at 1000 tokens/min and 429s an uncapped estimate of 1196, so Groq
endpoints carry `max_tokens: 800` (`setdefault`, caller wins). Live page proof:
`plan_source: llm:groq/qwen/qwen3.8-27b`, model-written intents, `pass 8/8`. Suite `162 passed`.

## Postscript 3: scenario 2 failed 6/9 under the model — refs assumed `latest`

Qwen planned the inbox job correctly (files_list -> 2x invoice_parse) but both parses died with
`unresolved argument reference: 'latest'`. Root cause in `llm_plan`: any step downstream of a read
step took `{{dep.latest.*}}` refs via `_upstream_args`, which assumes the dependency returns one
`latest` record (true of the intake tools, predicted as F3 in this report's F-findings). A file
*list* carries no `latest`, so the ref could never resolve. Fix: only a write step takes refs; a
read step after a read is asked for its own file (`_step_args`, upstream list in context).
Live proof on the page: `llm:groq/qwen/qwen3.8-27b`, `pass 9/9`, both invoices parsed for real.
Pinned by `test_a_read_step_after_a_list_names_its_own_file_instead_of_a_latest_ref`. Suite `163`.
