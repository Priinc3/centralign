# REPORT — Phase 12 real AI planning on Gemini/Gemma (NORMAL)

`--llm` no longer degrades. With a key in the environment the planner asks a real model, the model
answers, and the run says which model: **`plan: llm:gemini/gemma-4-31b-it`**, `pass 8/8`, the ERP
holding the invoice the read step actually found. Nothing is faked client-side: the plan is the
model's, and the two values the model could not know are resolved out of the find result, not made up.

## Criteria, one by one

| BUILD criterion | result | evidence |
|---|---|---|
| `make_plan(task, registry(), offline=False)` → `plan_source llm:gemini/*`, steps find→post, `finish_reason tool_calls` | ✅ | `plan_source: llm:gemini/gemma-4-31b-it`, `s1:invoice_find_latest -> s2:erp_post_invoice`, `finish_reason 'tool_calls'` (157 completion tokens) |
| `demo --llm` cold → `plan: llm:gemini/*`, not `heuristic(fallback…)`, still 8/8 | ✅ | `verdict: pass 8/8  replayed=1  plan: llm:gemini/gemma-4-31b-it`, `ERP count: 1` |
| UI `--llm` names a real model | ✅ | `phase=done banner='pass 8/8' src='llm:gemini/gemma-4-31b-it' erp=1` |
| Full suite green | ✅ | `154 passed, 1 skipped` (16 new) |
| No-key behaviour byte-identical (heuristic, offline) | ✅ | `verdict: pass 8/8  replayed=1  plan: heuristic`, and `--llm` with no key → `heuristic(fallback: LlmError: no usable LLM key: …)` |
| No new deps; keys never logged | ✅ | `python3 -m src.security.scan` → `findings: 0`; the key existed only in the shell environment |

## What was actually wrong: `title`, and only `title`

The BUILD (following Phase 09) suspected the pinned empty `args` object, or `$defs`, or `strict`.
Measured, **all three are innocent**. The one key `generativelanguage`'s function-call filter
rejects is `title` — which pydantic puts on every model in the schema. Deleting *only* those keys
makes today's strict schema return a real `tool_calls` step.

`_plan_submit_tool()` is therefore **unchanged**. The per-provider shape lives in the router, next to
the per-endpoint model name that was already there.

### Variants tried, live, with the measured `finish_reason`

OpenAI-compat endpoint (`…/v1beta/openai/`), `submit_plan` forced, full 1.3k-token manifest prompt:

| # | schema variant | model | `finish_reason` | out |
|---|---|---|---|---|
| A | **today's strict schema** (`strict:true`, `$defs`, `additionalProperties:false`, pinned `{}` args, titles) | gemini-2.5-flash | `function_call_filter: MALFORMED_FUNCTION_CALL` | 0 |
| B | A, `strict` dropped | gemini-2.5-flash | `function_call_filter: MALFORMED_FUNCTION_CALL` | 0 |
| C | A, `$defs` inlined (`$defs` key kept) | gemini-2.5-flash | `function_call_filter: MALFORMED_FUNCTION_CALL` | 0 |
| D | C, `args` dropped entirely | gemini-2.5-flash | `function_call_filter: MALFORMED_FUNCTION_CALL` | 0 |
| F | hand-built flat schema, no `additionalProperties` | gemini-2.5-flash | **`tool_calls`** | 142 |
| H | F + `additionalProperties:false` | gemini-2.5-flash | **`tool_calls`** | 136 |
| L | A, `$defs` inlined **and** `$defs` removed, no `strict`, no `additionalProperties` | gemini-2.5-flash | `function_call_filter: MALFORMED_FUNCTION_CALL` | 0 |
| L2 | L, `args` as a free-form object | gemini-2.5-flash | `function_call_filter: MALFORMED_FUNCTION_CALL` | 0 |
| L3 | L, `args` dropped entirely | gemini-2.5-flash | `function_call_filter: MALFORMED_FUNCTION_CALL` | 0 |
| L4 | L + `strict:true` + **titles dropped** | gemini-2.5-flash | **`tool_calls`** | 148 |
| L5 | **A with nothing changed but the titles dropped** | gemini-2.5-flash | **`tool_calls`** | 171 |
| — | **the shipped profile** (L5 + `temperature: 0`) | **gemma-4-31b-it** | **`tool_calls`** | **157** |

Every failing row has `completion_tokens: 0` — the request never reaches generation. `title` is the
only common factor: present in A–D/L/L2/L3, absent in L4/L5/the shipped profile.

The **native** endpoint (`generateContent`) is stricter and *says so*, which is how the cause was
identified rather than guessed. It rejects the same schema with a named field:

```
[native today]           HTTP 400  Unknown name "$defs" at 'tools[0].function_declarations[0].parameters'
[native today]           HTTP 400  Unknown name "additionalProperties" at '…parameters'
[native deref, no $defs] HTTP 400  Unknown name "additionalProperties" at '…parameters'
[native inlined, no addProps, args kept]        ACCEPTED  finishReason=STOP
```

So a *native* transport would need `$defs` inlined **and** `additionalProperties` gone. The compat
shim tolerates both, so the profile strips only `title` — the least change the measurement supports.

### The same key, three times: what it can and cannot do

```
key AIzaSy…1  429  "You exceeded your current quota"                (free tier exhausted)
key AQ.…2     OK   gemini-2.5-flash, gemma-4-26b-a4b-it, gemma-4-31b-it all listed + callable
key AIzaSy…3  403  "Permission denied: Consumer 'api_key:AIza…'"     (Gemini API not enabled)
```

Only the second key can plan. Free-tier quota is the real constraint on this box: ~15 RPM, so the
probes were paced at 9–12 s.

## The live transcript

**The shipped request**, built by the router profile and nothing else (key in the shell only):

```
model             gemma-4-31b-it
finish_reason     'tool_calls'
completion_tokens 157   prompt_tokens 1396
tool_calls        1 -> submit_plan
arguments         {"version":1,"goal":"find the latest invoice for Company X and post it to the ERP",
                   "steps":[{"id":"s1","tool":"invoice_find_latest","depends_on":[],"args":{}, …},
                            {"tool":"erp_post_invoice","success_criterion":"The invoice is successfully
                             posted to the ERP.","id":"s2","intent":"Post the details of the latest invoice
                             to the ERP.","args":{},"depends_on":["s1"]}]}
```

**`make_plan` on the live endpoint** — note the `retry` event: the shim 500'd mid-run and the same
request on the same key worked immediately after, which is exactly the case the retry exists for.

```
key slots: ['gemini#1']  model: gemma-4-31b-it
plan_source: llm:gemini/gemma-4-31b-it
steps:       s1:invoice_find_latest -> s2:erp_post_invoice
  s1 invoice_find_latest   args={"company": "Company X", "dir": "seed/invoices", "pattern": "*"}
  s2 erp_post_invoice      args={"action": "post", "vendor": "{{s1.latest.vendor}}",
                                "amount": "{{s1.latest.amount}}", "due_date": "{{s1.latest.due}}",
                                "source_file": "{{s1.latest.file}}", "base_url": "", …}
router events:
  {"key": "gemini#1", "attempt": 1, "outcome": "ok"}
  {"key": "gemini#1", "attempt": 1, "outcome": "retry", "status": 500, "reason": "Internal error encountered."}
  {"key": "gemini#1", "attempt": 1, "outcome": "ok"}
  {"key": "gemini#1", "attempt": 1, "outcome": "ok"}
```

**`demo --llm`, cold scratch** (`/tmp/centralign-demo` wiped on start, so run 1 is genuinely cold):

```
run 1  39c14ed7ed0c
  ✓ s1  invoice_find_latest    CX-2024-0912  $4,820.00 USD  due 2024-10-12
  ⏸ s2  erp_post_invoice       not posted — waiting for a human to approve it (queued below)
  ✓ 379562e02521  erp_post_invoice $4,820.00  approved by demo-operator
run 2  continuing 39c14ed7ed0c
  ↻ s1  invoice_find_latest    CX-2024-0912  $4,820.00 USD  due 2024-10-12
  ✓ s2  erp_post_invoice       ERP row #1 created

verdict: pass 8/8   replayed=1   plan: llm:gemini/gemma-4-31b-it   run: 543f405d4d5b
ERP count: 1
```

Repeated after every code change, including a final timed run: `pass 8/8  replayed=1  plan:
llm:gemini/gemma-4-31b-it  ERP count: 1`, `rc=0`, `wall clock: 159.2s`.

The row the model caused to be created, read straight out of the sim ERP:

```
ACME SUPPLY CO.|CX-2024-0912|4820.00|USD|2024-10-12|INV-X-2024-0912-acme.pdf
```

That is the invoice `invoice_find_latest` returned, byte for byte: `due_date` came from the record's
`due`, `source_file` from its `file`. Nothing in that row was written by a model.

**UI `--llm`**, driven over HTTP exactly as `tests/test_ui_offline.py` does:

```
POST /api/run      -> 202
  phase=awaiting banner='blocked / 7/8 predicates passed' src='llm:gemini/gemma-4-31b-it' erp=0 pending=1
  steps: [('s1','succeeded'), ('s2','skipped')]
POST /api/approve  -> 200  {"approved": {… "verdict": "granted", "amount": 4820.0 …}}
  phase=done     banner='pass 8/8' src='llm:gemini/gemma-4-31b-it' erp=1 pending=0
  steps: [('s1','cached'), ('s2','succeeded')]
  erp row: {"id": 1, "vendor": "ACME SUPPLY CO.", "invoice_number": "CX-2024-0912", "amount": "4820.00", …}
```

## Files changed

| file | change |
|---|---|
| `src/llm/router.py` | per-endpoint profile (`schema_mode`: `strict` \| `google`) + `_without_titles` / `_profile_tool`; `temperature: 0` default on google endpoints; one in-place retry for a transient 5xx when there is no other key; `last_endpoint` label; `GEMINI_MODEL` default is now `gemma-4-31b-it` |
| `src/runtime/planner.py` | `make_plan` names the serving endpoint (`llm:<provider>/<model>`); a step fed by a read step emits `{{dep.latest.field}}` refs instead of asking the model for values that do not exist yet (`_upstream_args`) |
| `tests/test_llm_gemini_planning.py` | new, 16 tests, offline — no key, no socket |

Rotation, cooldown, key-fault triage, the fatal-4xx rule and the redaction path are untouched; the
whole Phase 07 test file still passes untouched.

### Two departures from the frozen grant, both approved before the code was written

1. **`make_plan` (2 lines).** `plan_source` is built there, and no editable function could produce
   `llm:gemini/*` without it. Approved: `Router.last_endpoint` + the label.
2. **`llm_plan`'s per-step arg loop + `_upstream_args` (~18 lines).** Without this the criteria could
   not be met *honestly*: planning happens before anything runs, so `_step_args` asked the model for a
   post payload it had no way to know. It answered `INV-12345 / 1200.00 / 2016-12-21 /
   https://erp.example.com/api/v1`, the approval card and the re-plan then disagreed, and the demo
   stopped at 7/8 with a fabricated invoice queued for the ERP. Approved: emit the refs the executor
   already resolves (`executor.resolve_refs`, `planner.py`'s own offline path has used them since
   Phase 01). The model still chooses the tools, the order, the DAG and the success criteria; it is
   only no longer asked to know the future.

`_step_args` itself is unchanged, and is still what asks a model for a *root* step's arguments
(`dir`, `pattern`, `company`), where the model genuinely can help.

## Tests

```
$ python3 -m pytest tests/test_llm_gemini_planning.py -q
................                                                         [100%]
16 passed in 0.18s

$ python3 -m pytest tests/ -q
154 passed, 1 skipped in 15.13s          # 138 without this file, +16 here

$ python3 -m src.security.scan
scanning 6 trees for credentials  … none
allowlisted canaries  2  (tests/, marker-checked: the line must still say why)
findings: 0  → safe to publish
```

Pinned offline: the strict schema still has `strict:true`, `$defs`, `additionalProperties:false` and
the empty `args` object; the google profile removes *nothing but* `title` and every `required` name
still has a property (the invariant the endpoint's own validator used to reject); an OpenAI endpoint
receives the tool **byte-identical** and no imposed temperature; a Gemini endpoint receives it
title-free, `strict: true`, at `temperature: 0`; a 5xx is retried in place when there is no other
key and a 429 never is; `plan_source` reads `llm:gemini/gemma-4-31b-it`; a failure still degrades to
`heuristic(fallback: …)` with the heuristic plan intact; a key echoed by the endpoint rides out as
`[REDACTED]` and never into the plan source.

## Findings, limits, follow-ups

- **F1 — 🔴 rotate the key.** It is in this transcript in plain text (as in Phase 07). It lived only
  in the shell environment; `src/security.scan` proves no file holds it.
- **F2 — 🟠 the compat endpoint 500s intermittently.** Observed on plain text and on tool calls,
  roughly one request in three on `gemma-4-31b-it`, plus one read timeout. The in-place retry covers
  the single-key case, which is why `demo --llm` has been stable across repeated runs. With two or
  more healthy keys the cheaper retry is the failover and the 5xx costs a 60 s cooldown.
- **F3 — 🟠 `gemma-4-31b-it` is slow.** ~1.3k-token manifest prompt in, ~30–60 s per call; the UI needs
  90–100 s to reach the approval card (measured by polling) and the whole two-run `demo --llm` cycle
  takes **159 s** wall clock, because resuming re-plans. `GEMINI_MODEL=gemini-2.5-flash` is several
  times faster on the same key and accepts the same schema — the demo story does not depend on gemma,
  so the video beats should budget the wait or name the faster model.
- **F4 — 🟠 sampled decoding is not a planner.** At the endpoint's default temperature the same
  prompt produced a 1-step plan, a 5-step plan including `browser_open`, and a plan naming a tool
  that does not exist (`invoice_post_erp` → the honest `LLM invented tools not in the manifest`
  fallback). `temperature: 0` on google endpoints: three consecutive correct plans. A caller's own
  temperature still wins.
- **F5 — 🟡 a native transport would be a different profile.** `generateContent` rejects `$defs` and
  `additionalProperties` outright; the shim accepts them. If the shim is ever retired, `_profile_tool`
  is the single place that has to grow (`SCHEMA_GOOGLE_NATIVE`: inline `$defs`, drop
  `additionalProperties`) — nothing else in the planner would change.
- **F6 — 🟡 refs assume a `latest` record.** `_upstream_args` maps an arg to `{{dep.latest.<field>}}`,
  which is the shape `invoice_find_latest` returns. A second result shape needs a mapping row; the
  alias table (`due_date`→`due`, `source_file`→`file`) is where it goes.
- **F7 — 🟡 `base_url` / `idempotency_key` are left blank by name.** Those two are the manifest's
  business (the tool fills its own default), never a field read out of a record. If a future write
  tool has a data field that must *not* come from upstream, it needs adding to `_NOT_FROM_RESULT`.
- **F8 — 🟡 concurrent writer.** Phase 13 (UI story) is editing `src/ui/app.py` and
  `tests/test_ui_offline.py` right now; the UI transcript above was measured against `app.py` as of
  00:03 and the UI test file as of 00:17 (11 tests). Suite counts move for that reason, not mine.
- **F9 — 🟡 docs drift, for whoever owns them next.** `README.md` / `SUBMISSION.md` / `docs/USER-TEST.md`
  quote older suite counts and describe `--llm` as degrading to the heuristic plan. The suite is
  **154 passed, 1 skipped**, the Gemini endpoint's default model is **`gemma-4-31b-it`**, and `--llm`
  now names a real model. `docs/USER-TEST.md` step 13 and Phase 07's F2 are both stale for that
  reason.

## Notes for the reviewer

- The router already rewrote `model=` per endpoint; the schema profile is the same idea applied to
  the other provider-specific field in that call, so `_plan_submit_tool` stays the single frozen
  contract and one provider's filter can never leak into another's.
- The retry is deliberately the *last resort only* (`attempt == len(order)`). With another healthy
  key, failing over is both the cheaper retry and the behaviour Phase 07 pinned — that test file is
  untouched and still green.
- `plan_source` is now evidence, not a label of our own: it is the model id the endpoint actually
  served with, read back off the router after the call.