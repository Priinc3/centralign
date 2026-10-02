# REPORT — Phase 14 packet sync (NORMAL, docs-only, pre-record)

Type NORMAL, no siblings. The exception granted was four files — `README.md`, `SUBMISSION.md`,
`docs/USER-TEST.md`, `demo/video-script.md` — for numbers, `--llm` truth and the UI run-order. **I
edited three of them; `demo/video-script.md` needed nothing** (proof below). No code, no tests, no
schema. Source of truth: 12's and 13's REPORTs, 10's role line.

```
 README.md            133→156 (×3), ~11s→~16s, the --llm quickstart note,
                      the planning row + "What the LLM path has actually been exercised on"
 SUBMISSION.md        133→156 (×3), the same section, "What a reviewer should run, in order"
                      → UI page first (11's parked item)
 docs/USER-TEST.md    7.30s→15.81s + "about 7 seconds"→"about 16 seconds", step 13 rewritten,
                      the §0 key table row, the step-13 tick box, the known-quirk row
 demo/video-script.md not edited — 13 had already synced every number and every --llm sentence
```

## 1. Criterion: zero stale numbers

```
$ grep -rn "133 passed\|133 tests" README.md SUBMISSION.md docs/ demo/
$ echo $?
1
```

Empty, which is the BUILD's criterion. Every count the four publishable docs now claim, and where:

```
README.md:74          Full suite (156 tests, ~16s) and the pre-publish security scan:
README.md:262         tests/           156 tests, offline, no API key
README.md:272         $ python3 -m pytest tests/ -q       → 156 passed, 1 skipped
SUBMISSION.md:13      - **Proof:** … → 156 passed · … 0 findings
SUBMISSION.md:46      … This is the demo, the video, and the 156 tests.
SUBMISSION.md:84      python3 -m pytest tests/ -q           # 156 tests
docs/USER-TEST.md:367 156 passed, 1 skipped in 15.81s
docs/USER-TEST.md:370 It takes about 16 seconds …
docs/USER-TEST.md:376 - [ ] step 9: `156 passed, 1 skipped`, no key exported
demo/video-script.md:6,200,243,402,405,406   (unchanged by me — 13 set these)
```

`156` and `~16s` are this session's measurements, not carried over: `156 passed, 1 skipped in
15.81s`, then `15.83s` on a second run (13 measured 15.77s). The timing line in USER-TEST now
says so explicitly — the count is the part that must match, the seconds are one laptop run. Same
wording 13 already used in the script.

Every remaining `127` in these files is `127.0.0.1`, and every remaining `133`/`127` *count* in the
repo is a labelled historical appendix outside the grant and outside the grep:
`prompts/phase-08-submission/USER-STEPS.md:6,89,112` says "State as of the phase-08 build" and is
how 08's own REPORT is meant to read.

## 2. `--llm`, told the way 12 measured it

The F2-era sentence — *Gemini refuses our strict schema, so `demo --llm` ends
`plan: heuristic(fallback: PlannerError: LLM returned no tool call)`* — was in three files. It is
false as of 12 and it undersold the system, so it is replaced everywhere by the same four beats:

| beat | what the docs now say | 12's evidence |
|---|---|---|
| it really plans | `plan: llm:gemini/gemma-4-31b-it`, `finish_reason: tool_calls`, still `pass 8/8`; the model picks tools, order, DAG, success criteria | `phase-12/REPORT.md:12-14, 80-88, 120` |
| it is not inventing data | the posting step emits `{{s1.latest.amount}}` / `{{s1.latest.due_date}}`, the executor resolves them from the read step's own result, so the ERP row is `ACME SUPPLY CO.\|CX-2024-0912\|4820.00\|USD\|2024-10-12` | 12:100-101, 127-134 |
| what it took | eleven schema variants, `MALFORMED_FUNCTION_CALL` on all the ones that kept `title`; the shipped fix removes **only** `title`, keeps `strict: true`, sets `temperature: 0`; an OpenAI endpoint still gets the tool byte-identical | 12:33-46, 191-198 |
| the honest ceiling | ~30–60 s per call on `gemma-4-31b-it`, 159 s for the two-run cycle; compat endpoint 500s ~1 request in 3, retried in place when there is one key; free-tier quota is the real constraint | 12:125, 204-212 |

`strict` is still never stripped, and both files now say that in the same breath as the fix — the
guarantee was worth more than the demo looking clever, and a reviewer who reads only the fix line
should not be left thinking it was traded away.

`USER-TEST.md` step 13 got the most work, because it is the only place a user is told to spend
their own key and their own minutes:

- the expected line is now `plan: llm:gemini/gemma-4-31b-it`, not `plan: llm`, with the note that
  the string is read back off the router after the call — evidence, not a label we printed;
- `GEMINI_MODEL` is documented as **optional** (`src/llm/router.py:57` defaults to
  `gemma-4-31b-it`); the old comment claimed `gemini-2.5-flash` *was* the default;
- a timing paragraph up front — 30–60 s per call, budget minutes, or use flash;
- the three fallback conditions a user can actually hit (no key, free-tier 429, refused key 400),
  plus 12's F2 500s, all with the honest framing that a 429 and a schema refusal look identical
  from the outside unless you read the reason;
- `tests/test_llm_gemini_planning.py -q  # 16 passed` added next to the router's 12, so the schema
  profile can be verified with no key at all;
- **05/FIX-2 is still open and is now named as open**, not as a caveat: `src/cli/main.py:508` is
  still `args.offline or not os.environ.get("OPENAI_API_KEY")`, so `cli.main run --task …` still
  needs `OPENAI_API_KEY` even with a Gemini key exported. The step tells the reader to use
  `demo … --llm` or the page, and cites the unapplied FIX-2 file.

The §0 key table and the known-quirks table were corrected the same way. The quirk row used to say
live LLM planning "needs a schema Gemini accepts (open item)" — it no longer does, and the row now
says which reason string means *this machine* versus *the endpoint refused the plan*, with one new
row for `--llm` being slow rather than broken.

## 3. Run-order: the page first (11's parked item)

`SUBMISSION.md` "What a reviewer should run, in order" now starts with
`python3 -m src.ui.app --port 0`, and says why in one line: the page is the demo and the video
surface, and it is the same loop the terminal runs. `bash demo/run.sh` is second, unchanged. Below
the block, the three clicks are spelled out with the real button labels read out of
`src/ui/index.html:115,277,344` (`Run the task` → `Approve` → `Run again (run N)`), the amber
`blocked / 7/8 predicates passed`, the `$4,820.00` card, green `pass 8/8   replayed=1` and
`replayed=2` with the ERP still at one row, plus `/tmp/centralign-ui` wiped on startup and
localhost-only binding. Nothing was invented for it — I drove it, over HTTP, on this tree:

```
GET /api/state -> 200   scenarios: ['intake', 'inbox', 'check']
POST /api/run     -> 202   awaiting  blocked / 7/8 predicates passed   erp 0
POST /api/approve -> 200   done      pass 8/8                         erp 1
   erp row  {"id": 1, "vendor": "ACME SUPPLY CO.", "invoice_number": "CX-2024-0912",
             "amount": "4820.00", "currency": "USD", …}
POST /api/run     -> 202   done      pass 8/8                         erp 1
   tools_replayed ['erp_post_invoice', 'invoice_find_latest']   (nothing executed twice)
```

The one `run` command that stops at `blocked / 7/8` keeps its existing explanation — it is the gate
working, not a broken command.

**10's role line is untouched**, verified as a string compare against the copy 10 filed in its own
REPORT, not just a grep:

```
SUBMISSION.md:3 -> 'Role: AI Engineering Intern (prototype also demonstrates Founding-scope architecture — see video close)'
phase-10 copy   -> 'Role: AI Engineering Intern (prototype also demonstrates Founding-scope architecture — see video close)'
identical: True
```

Intern-first ordering still holds in both places it is supposed to (`SUBMISSION.md:3`,
`demo/video-script.md:215`), and 10's closing beat in the script is intact from line 211.

## 4. `demo/video-script.md` — verified, not edited

13 had already synced it, so the honest outcome for this file is a grep rather than a diff. Every
number is `156`, the timing is labelled as one measured run (`15.85s`, "a few tenths either side",
"`156 passed` is the part that must not move"), and the `--llm` copy is already true: it names
12's live `llm:gemini/gemma-4-31b-it`, warns to budget ~30–60 s per call, and tells the operator to
say out loud that *this* take had no key so the deterministic fallback is what the badge means.

```
$ grep -rn "133\|127 passed\|127 tests" demo/video-script.md
$ echo $?
1
$ grep -n "gemma-4-31b-it\|30–60s\|fallback" demo/video-script.md
168:  `plan_source`. With a key exported and `--llm` it names the model that wrote the plan
169:  (`llm · gemini/gemma-4-31b-it`); with no key it says `heuristic offline`, or names the reason it
380:  plan_source: heuristic(fallback: LlmError: no usable LLM key: …)
492: (`llm · gemini/gemma-4-31b-it`) — and budget ~30–60s per call, because the page does not fake a
```

Editing it anyway would have been motion, not work.

## 5. Which model the video take should use — the honest line

**Keep the video take unkeyed (the deterministic page run), exactly as the script is written.** The
page run is 0.4 s, deterministic, and the badge reads `heuristic offline`; the script already tells
the camera operator to say that no model drove *this* run. If a keyed take is wanted for the
badge, use `GEMINI_MODEL=gemini-2.5-flash` — 12 measured it accepting the same title-free schema
(variants A–L5 all ran on flash) while the shipped default `gemma-4-31b-it` costs 30–60 s per call
and 159 s for the two-run cycle. A `gemma` take buys one thing flash also has (a named model on
screen) at several times the wait.

**The BUILD asked for one measured cold `GEMINI_MODEL=gemini-2.5-flash` `--llm` take for timing. I
could not take it, and the reason is the box, not the code.** This session's only credential is
`GOOGLE_API_KEY`, which the Gemini endpoint refuses (13 measured the same). I ran the take anyway
with that value exported as `GEMINI_API_KEY` so the failure would be on the record rather than
assumed, and it degraded exactly as documented:

```
$ GEMINI_API_KEY="$GOOGLE_API_KEY" bash demo/run.sh /tmp/p14flash --llm
run 1  015734d526b3
  ✓ s1  invoice_find_latest    CX-2024-0912  $4,820.00 USD  due 2024-10-12
  ⏸ s2  erp_post_invoice       not posted — waiting for a human to approve it (queued below)
run 2  continuing 015734d526b3
  ↻ s1  invoice_find_latest    CX-2024-0912  $4,820.00 USD  due 2024-10-12
  ✓ s2  erp_post_invoice       ERP row #1 created

verdict: pass 8/8   replayed=1   plan: heuristic(fallback: LlmError: no usable LLM key: …)   run: 73363b6c60df
ERP count: 1
rc=0

# run 1 evidence, limits[0]:
planner=heuristic(fallback: LlmError: all 1 LLM key(s) failed, last on gemini#1: Error code: 400 -
[{'error': {'code': 400, 'message': 'Please pass a valid API key', 'status': 'INVALID_ARGUMENT'}}])
```

So: **flash timing on this machine is unmeasured.** The `several times faster` claim in the docs is
12's, measured on a key this box does not have, and I left it attributed rather than re-asserting
it as fresh. Anyone with a live key can close it in one command; the number belongs in 12's REPORT
as an addendum, not in a docs file.

Nothing was reshot, re-timed or re-recorded for this — 13's F1 (the page's top third changed, so
the 0:05 and 0:37 beats need one re-record) is untouched and still open.

## 6. Full suite untouched, and green

```
$ python3 -m pytest tests/ -q
156 passed, 1 skipped in 15.81s          # and 156 passed, 1 skipped in 15.83s

$ python3 -m src.security.scan
findings: 0  → safe to publish

$ bash demo/run.sh /tmp/p14v | grep -E "^verdict|^ERP count"
verdict: pass 8/8   replayed=1   plan: heuristic   run: 87409256b637
ERP count: 1
```

No code or test file was opened for writing. `git status --short` shows the same set as before this
phase — `README.md`, `SUBMISSION.md`, `docs/USER-TEST.md` (mine) alongside 12/13's uncommitted
`src/llm/router.py`, `src/runtime/planner.py`, `src/ui/`, the two new test files and
`demo/video-script.md` (theirs). A docs-only phase cannot break the suite; the counts are quoted
because a user-runbook number that is wrong is worse than no number.

## 7. Findings

- **F1 — 🟠 the last `--llm` truth surface outside this grant is the code's own help text.**
  `src/ui/app.py:438-440` still describes `--llm` as "unkeyed, it degrades to the deterministic
  heuristic plan exactly as the CLI does", and the page's startup line (`src/ui/app.py:449`) prints
  `planner heuristic (offline, no key needed)` or `planner LLM when a key is set`. Both are *true*
  and both now undersell it — neither says a real model may answer and name itself on the badge.
  Code is out of this BUILD's scope; it belongs to whoever next opens `src/ui/app.py`.
- **F2 — 🟠 05/FIX-2 is still unapplied** (`src/cli/main.py:508`, `OPENAI_API_KEY` only), so
  `cli.main run` cannot reach a Gemini-only owner. Now documented in USER-TEST as an open item
  rather than a caveat. One line plus one test, per `prompts/phase-05-demo-ux/FIX-2.md`.
- **F3 — 🟡 `prompts/phase-08-submission/USER-STEPS.md` still prints `127 passed, 1 skipped`** in
  three places. Deliberately left: it is a labelled phase-08 snapshot outside the grant and outside
  the BUILD's grep, and rewriting a historical report is how reports start lying. Flag it if the
  packet is ever published as a whole rather than by pointer.
- **F4 — 🟡 `docs/USER-TEST.md` line 3 still says "Twelve commands"** while the file has thirteen
  steps, one of them optional. Pre-existing, harmless, and not a number the BUILD granted; left
  rather than widened.
- **F5 — 🟡 `hitl.decide` writes `decided_on = request_id`** (11's finding, still open, 13's F5).
  Not quoted in any of these docs; mentioned only so it does not get lost between phases.

skipped: adding a `--llm` line to README's "Proven, not claimed" block. The count and verdict
lines there are meant to be five commands a reviewer can paste; a line that needs a key and two
minutes of model latency would break that contract. The live claim lives in the LLM section
directly above, with its transcript cited.

skipped: re-recording or re-timing anything. Out of scope for a docs phase and 13's F1 owns the
re-record decision.

## Out of scope, untouched

Code, schema, `context/*.yaml`, tests, `prompts/phase-08-submission/USER-STEPS.md`, and the terminal
transcripts in README that `demo/run.sh` still prints byte for byte. F3 from 12 remains open and
unowned: a native `generateContent` transport would need `$defs` inlined and
`additionalProperties` dropped — one function, `_profile_tool`, if the shim is ever retired.