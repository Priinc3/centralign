# REPORT — Phase 01 runtime (G1)

State: **DONE** (re-verified green after FIX-1, appended below). Contracts frozen, loop + ledger +
evidence shipped, 17 tests pass, offline demo <0.2s.

## Files changed (OWN only)

| File | Lines | What |
|---|---|---|
| `src/contracts/tools.py` | 144 | `ToolManifest` (name/description/parameters/risk/idempotent/requires_approval/side_effect_free), `RISK_TIERS`, `openai_tool()` (strict:true), `strict_parameters()` (optional→nullable+required), `api_name()` (dots→`_` at the API boundary), `validate_args()` |
| `src/contracts/events.py` | 110 | `Event` envelope (run_id/seq/ts/type/actor/step_id/tool/payload/error), 14 event types, `redact()` |
| `src/contracts/verdict.py` | 81 | `Predicate` (kind/statement/expected/actual/passed/weight/evidence_ref), `Verdict` (pass/fail/blocked + `from_predicates`) |
| `src/runtime/planner.py` | 385 | `Plan`/`Step` pydantic DAG (dup/cycle/unknown-dep validation, Kahn `topo_order`), `strict_schema()`, `heuristic_plan()`+`fill_args()`, `llm_plan()` (2-phase strict tool-calling), `make_plan()` with silent-free fallback |
| `src/runtime/executor.py` | 148 | manifest-only dispatch, schema gate, idempotent replay, optional `authorizer` hook for Phase 03, failures-as-data |
| `src/runtime/loop.py` | 436 | 8 stages, `state.json` checkpoint per step, verify predicates, `run_task()`, CLI, `load_registry()` (Phase 02 adapter) |
| `src/ledger/store.py` | 211 | SQLite WAL (`journal_mode=WAL, synchronous=NORMAL, busy_timeout=5000`), append-only `steps`(per attempt)/`events`, `idem_key()`, `runs` |
| `src/ledger/evidence.py` | 86 | atomic `evidence.json` + `events.jsonl` + `tools.json`, `write_state()`, `load_evidence()` |
| `tests/test_runtime_smoke.py` | 325 | 13 tests, fake tools, no LLM key, no network |

Not touched: `src/tools/*`, `sim_app/*`, `data/seed/*` (02), `src/memory/*`, `src/policy/*`, `context/*` (03), `src/contracts/*` read-only for them.

## Commands + raw output

```
$ python3 -m pytest tests/test_runtime_smoke.py -q
.............                                                            [100%]
13 passed in 0.05s

$ python3 -m src.runtime.loop --task "demo" --offline --tools demo
run e0c471a7c3cc [completed] verdict=pass plan=heuristic
dag: s1:echo_note
steps: ['succeeded']
evidence: runs/e0c471a7c3cc/evidence.json
state:    runs/e0c471a7c3cc/state.json
exit=0

### no-network proof (socket.connect/create_connection blocked for the whole run)
rc=0 elapsed=0.008s, socket.connect blocked for the whole run

### evidence.json
keys:   ['bundle_version', 'events', 'limits', 'plan', 'run', 'steps', 'tools', 'totals', 'verdict', 'written_at']
steps:  [('s1', 'echo_note', 'succeeded')]
verdict: pass | 6/6 predicates passed
predicates: [('plan_has_steps', True), ('every_step_resolved', True), ('no_silent_skips', True),
             ('each_success_has_evidence', True), ('audit_trail_complete', True), ('criterion:s1', True)]
```

Note: this box has no `python` on PATH, only `python3` — use `python3 -m ...`.

## Verify steps (how to re-check)

1. `python3 -m pytest tests/test_runtime_smoke.py -q` → 13 passed.
2. `python3 -m src.runtime.loop --task "demo" --offline --tools demo` → `runs/<id>/evidence.json` + `state.json` + `events.jsonl` + `tools.json`, exit 0.
3. Idempotency: run it twice with the same task and registry → second run's steps are all `cached`, zero tool calls (`test_second_run_replays_instead_of_re_executing`).
4. Isolation: `test_failing_tool_is_isolated_retried_once_and_verdict_fails` → `['succeeded','failed','skipped']`, failed step retried once (attempt 1+2 rows), dependent step skipped with a reason, verdict `fail`.
5. Never silently executes: unknown tool / bad args / approval-required are all `skipped` with a reason, and the callable is never called (`test_unknown_tool_and_bad_args_are_never_executed`, `test_policy_approval_blocks_before_execution`).
6. Secrets: `test_secrets_are_never_written_to_the_bundle` → `api_key` value is `[REDACTED]` in the event log.
7. WAL/append-only: `PRAGMA journal_mode == wal`, `busy_timeout == 5000`, duplicate `(run,step,attempt)` raises `IntegrityError` (attempts append, never update).

## Frozen contract summary (for 02/03/04/05/06)

- `ToolManifest`: `name` (dots allowed), `description`, `parameters` (accepts `input_schema` alias), `risk: read|write|destructive`, `idempotent`, `requires_approval`, `side_effect_free`. `openai_tool()` is what you send to the API; `validate_args(manifest, args) -> list[str]` is what the executor enforces.
- Optional args: keep them optional in your manifest. `strict_parameters()` turns them into `["<type>","null"]` + required, which is how strict mode expresses optional.
- Dotted names (`erp.post_invoice`) need no rename: `api_name()` = `erp_post_invoice` is what the LLM sees; the runtime maps back to the real name.
- `Event.new(run_id, type, actor=..., payload=...)` — already redacted; `seq` is assigned by the ledger on append.
- `Predicate`/`Verdict`: Phase 04's verifier must emit these; a verdict is `pass` only when every non-zero-weight predicate passed.
- Registry API the loop calls (Phase 02): `registry()` or `load()` → `{name: ToolManifest}`, plus `callables()` → `{name: fn}`. Fallback path also accepts `manifests()` + `execute(name, args)` (converts their `{"ok": false}` convention into an exception).

## Limits / known gaps (honest)

1. **LLM path is unexercised** (no API key in this environment): `llm_plan()` is contract-correct but untested against the real API; any failure degrades to `heuristic` and records `plan_source=heuristic(fallback: ...)` in the bundle.
2. **Heuristic planner is keyword-overlap only** (name tokens, or 2+ content words in the description). If nothing matches it runs the lowest-risk tool and says so in the step `intent` — visible in evidence, not silent.
3. **No approval channel in Phase 01**: `authorizer` returns `approve` → step is `skipped` ("blocked: approval required") and the verdict is `blocked`. Phase 03's gate plugs into `Executor(authorizer=...)`; wiring it into `run_task` is B1 integration work.
4. **`Step.args` is runtime-populated on the LLM path**: strict mode cannot express a free-form map, so `submit_plan` pins `args: {}` and the planner issues one forced tool call per step against that step's own manifest. Cost: N+1 LLM calls per plan.
5. **Adapt = one retry, topological order** (`MAX_ATTEMPTS = 2`). No backoff, no replan — Phase 04 owns that.
6. **`validate_args` and `redact` are hand-rolled** (no `jsonschema` on the approved dep list). `validate_args` covers type/required/enum/additionalProperties only; `redact` is pattern-based, not a real secret scanner — Phase 06 hardens.
7. **Result passing downstream is textual**: upstream step results go into the per-step LLM call as context and the LLM maps them onto declared args. No `{{steps.s1.result.x}}` templating.
8. **Determinism**: same task + manifests + ledger ⇒ same plan and verdict; `run_id` and timestamps are UUID/clock, so bundle bytes differ per run. Verified by replay, not by byte-compare.

## Findings for siblings (posted in COMM.md)

- **02**: `files.list` `run()` needs `args["action"] = "list"`; with `dir`/`pattern` only it raises `KeyError: 'path'` (my loop correctly records it as a failed step, verdict=fail). `src/tools/__init__.py` also exported a stale `manifests` name for a while.
- **02**: `invoice.find_latest` raised `KeyError: 'path'` on the first integration probe (same shape of bug).
- **03**: "NAME_RE needs dots" — answered: dots are allowed in internal names, sanitized only at the API boundary. No change needed on your side.

## Help needed

None blocking. B1 integration should wire Phase 03's `policy.gate` into `Executor(authorizer=...)` and re-run `run_task("invoice intake")` with `--tools auto` once 02's tool bugs above are fixed.

---

# FIX-1 — B1 blockers F1/F2/F3/F4 (F2 🔴, F1/F3 🟠, F4 🟡)

Scope kept: `src/runtime/*`, `src/ledger/*` + `tests/test_runtime_smoke.py` (assertions that
*encoded* the bugs had to move, plus 4 new regression tests). Not touched: `src/tools/*`,
`src/memory/*`, `src/policy/*`, `context/*`, `src/contracts/*`, `sim_app/*`, `data/*`.

## Files changed

| File | Fix | What |
|---|---|---|
| `src/runtime/executor.py` | F2 | `payload_failed()`; a `{ok:false}` return records `failed` with `error=result["error"] or "tool returned ok:false (status=…)"` (result payload still stored). `StepResult.ok` is now `status=="succeeded" and not payload_failed`; new `StepResult.resolved` = succeeded-or-cached-and-not-failed, used by the loop's dependency gate so idempotent replay still works. New `resolve_refs()` resolves `{{s1.latest.amount}}` out of the dependency's recorded result *before* `validate_args`, and raises → `failed` ("unresolved argument reference") instead of posting a literal `{{…}}`. |
| `src/ledger/store.py` | F2 | `find_by_idem()` refuses to return a row whose stored result is an `{ok:false}` envelope, however it was written (rows from before this fix are not replayed as `cached` green). |
| `src/ledger/evidence.py` | F4 | `totals.tools_actually_executed` = tools with `status=="succeeded"` only (executed in *this* run); new `totals.tools_replayed` + `totals.cached` so the replay is still visible. |
| `src/runtime/planner.py` | F1/F3 | `_AFTER_RE` stops at the first clause boundary (was greedy to end-of-task). `_company()` = quoted name or `Company X` regex, else omitted (never the task tail). `fill_args` routes `company`/`company_name` through it. New `intake_plan()` templates the one flow worth templating offline: `s1:invoice_find_latest -> s2:erp_post_invoice`, find args `{company, dir: seed/invoices, pattern: *.pdf}`, and every post payload value is a `{{s1.latest.*}}` reference (`amount`/`vendor`/`due_date`/`invoice_number`/`currency`/`source_file`) — nothing mined from the task. `base_url`/`idempotency_key` stay empty so the tool's own defaults ($ERP_URL / payload hash) apply. Generic path now orders reads before writes (stable sort on risk). Empty task → empty plan. |
| `src/runtime/loop.py` | F3 | New gate predicate `non_empty_goal`; an empty task yields verdict `blocked` with summary `No task given` (run status `blocked`, CLI rc=1). Dependency gate and per-step `criterion:*` use `StepResult.resolved`; `execute()` passes `upstream=` so refs can resolve. |
| `tests/test_runtime_smoke.py` | all | 13 → 17 tests. `tools_actually_executed == []` on the replay run (was the F4 assertion), plus `test_ok_false_payload_is_failed_and_never_replayed`, `test_executor_resolves_upstream_refs_and_records_concrete_args`, `test_offline_planner_plans_invoice_intake_find_then_post`, `test_empty_task_blocks_instead_of_passing`. |

## Verify commands + raw output

### Suite
```
$ python3 -m pytest tests/ -q
.................................................s.                      [100%]
50 passed, 1 skipped in 2.17s
```
(the 1 skip is pre-existing: playwright absent)

### F1 — heuristic plans invoice intake, offline, end to end
```
$ python3 -m src.runtime.loop --task "find latest invoice from Company X and post it to the ERP" \
    --offline --tools auto --runs /tmp/opencode/v/r1
run f6de8e171d8a [completed] verdict=pass plan=heuristic
dag: s1:invoice_find_latest -> s2:erp_post_invoice
steps: ['succeeded', 'succeeded']
rc=0

$ python3 -c "... print evidence.json steps + verdict ..."
verdict: pass | 8/8 predicates passed
predicates: [('non_empty_goal', True), ('plan_has_steps', True), ('every_step_resolved', True),
             ('no_silent_skips', True), ('each_success_has_evidence', True), ('audit_trail_complete', True),
             ('criterion:s1', True), ('criterion:s2', True)]
totals: {"cached": 0, "events": 10, "failed": 0, "skipped": 0, "steps": 2, "succeeded": 2,
         "tools_actually_executed": ["erp_post_invoice", "invoice_find_latest"], "tools_replayed": []}
s1 invoice_find_latest succeeded | depends_on: [] | args: {"company": "Company X", "dir": "seed/invoices", "pattern": "*.pdf"}
s2 erp_post_invoice   succeeded  | depends_on: ['s1'] |
   args: {"action": "post", "amount": "4820.00", "base_url": "", "company": "Company X", "currency": "USD",
          "due_date": "2024-10-12", "idempotency_key": "", "invoice_number": "CX-2024-0912",
          "source_file": "INV-X-2024-0912-acme.pdf", "vendor": "ACME SUPPLY CO."}

$ curl -s localhost:8901/invoices
{"count": 1, "invoices": [{"id": 1, "idempotency_key": "inv-8e41e8ea926c4efb4a4836cb",
  "vendor": "ACME SUPPLY CO.", "company": "Company X", "invoice_number": "CX-2024-0912",
  "amount": "4820.00", "currency": "USD", "due_date": "2024-10-12",
  "source_file": "INV-X-2024-0912-acme.pdf", "created_at": "2026-10-02 06:42:42"}]}
```
`count: 1` — one row, and it is the same `idempotency_key` the earlier direct-tool probe created, so
the loop's post is the idempotent replay of it (`created: false`), not a second invoice.

Re-running the same task is a pure ledger replay and adds no ERP row:
```
$ for i in 1 2; do python3 -m src.runtime.loop --task "find latest invoice from Company X and post it to the ERP" \
      --offline --tools auto --runs /tmp/opencode/idem-runs; done | sed -n '1,3p'
run 64be57a38a7c [completed] verdict=pass plan=heuristic
dag: s1:invoice_find_latest -> s2:erp_post_invoice
steps: ['succeeded', 'succeeded']
run bbd338578dd3 [completed] verdict=pass plan=heuristic
dag: s1:invoice_find_latest -> s2:erp_post_invoice
steps: ['cached', 'cached']
$ curl -s localhost:8901/invoices   ->  ERP count: 1 ['inv-8e41e8ea926c4efb4a4836cb']
```

### F2 — `{ok:false}` is `failed`, and is never replayed as green
Corrected probe (real signature `Executor(ledger, run_id, manifests, callables)`, `lambda **a`):
```
run1: failed | ok: False | resolved: False | error: amount not a number: 'Company X...'
rows: [('s1', 'failed')]
run2 (replay): failed | ok: False | from_run: None <- not cached+ok
run3 (replay): failed | ok: False | from_run: None
```
Before the fix the same probe printed `succeeded | ok: True`, stored a `succeeded` row, and replayed
`cached | ok: True` (baseline reproduced, then fixed).

Through the loop, against a stub ERP that answers `422` on `POST /invoices`:
```
$ ERP_URL=http://127.0.0.1:8902 python3 -m src.runtime.loop \
    --task "find latest invoice from Company X and post it to the ERP" --offline --tools auto
run dd7203edc257 [failed] verdict=fail plan=heuristic
dag: s1:invoice_find_latest -> s2:erp_post_invoice
steps: ['succeeded', 'failed']
rc=1

verdict: fail | 6/8 predicates passed
failed predicates: ['every_step_resolved', 'criterion:s2']
s2 erp_post_invoice failed | error: amount not a number: '4820.00'
attempts in ledger for s2:  s2 attempt 1 failed | amount not a number: '4820.00'
                          s2 attempt 2 failed | amount not a number: '4820.00'   (adapt retried once)
tools_actually_executed: ['invoice_find_latest']
```
The two pre-fix poisoned rows in `runs/_ledger.sqlite3` (`d7b082ade67c` 422 stored as `succeeded`,
`f49672b3a8ff` replayed from it as `cached`) are still on disk — append-only, never rewritten — and
`find_by_idem` now refuses to serve them, so a re-run of that task executes again instead of
laundering the 422.

### F3 — empty task is blocked, not green
```
$ python3 -m src.runtime.loop --task "" --offline --tools demo
run 52c937228ab2 [blocked] verdict=blocked plan=heuristic
dag: (no steps)
steps: []
rc=1

run status: blocked | verdict: blocked | No task given
plan steps: []
predicates: [('non_empty_goal', False, False), ('plan_has_steps', False, 0),
             ('every_step_resolved', True, 0), ('no_silent_skips', True, 0),
             ('each_success_has_evidence', True, 0), ('audit_trail_complete', True, 1)]
```

### F4 — cached is not counted as executed
```
$ for i in 1 2; do python3 -m src.runtime.loop --task "demo" --offline --tools demo --runs /tmp/opencode/f4-runs; done
4c37690b7fd4 | steps: ['succeeded'] | tools_actually_executed: ['echo_note'] | tools_replayed: []
fc15d31426f6 | steps: ['cached']    | tools_actually_executed: []         | tools_replayed: ['echo_note']
```

### Regression: offline demo still passes with sockets blocked
```
$ python3 -c "... block socket.connect/create_connection, then run_task('demo', offline, tools='demo') ..."
run 130d7057c268 [completed] verdict=pass plan=heuristic
steps: ['succeeded']
rc=0 elapsed=0.009s, socket blocked for the whole run
```

## Deviations from FIX-1.md (deliberate, both verified)

1. **`dir: "seed/invoices"`, not `"data/seed/invoices"`.** `files_tool.safe_path()` resolves
   relative to `data/`, so `"data/seed/invoices"` becomes `data/data/seed/invoices` → `FileNotFoundError`
   (the failure F1 reported). The intent ("the seed invoices dir, never task text") is kept.
2. **Predicate count is 8, not 7.** The happy path now has 6 gates + 2 `criterion:*` steps; F3 added
   the `non_empty_goal` gate. Verdict is still `pass`, all 8 predicates `True`.
3. **`currency` is also a `{{s1.latest.currency}}` ref** (not listed in FIX-1, but filling it from
   the task text would post the company's name as the currency). Result: `USD`, matching the seed
   expectation. `base_url`/`idempotency_key` are left empty so the tool's own defaults apply.

## Remaining limits (honest)

1. **The `{{step.field}}` ref is the only data path between steps** (FIX-1 limit 7 stands for
   everything else): one dotted path, no defaults, no interpolation. A ref the upstream result does
   not carry fails the step loudly instead of guessing.
2. **Only the intake flow is templated offline.** Every other task still gets keyword-overlap tool
   choice plus text-mined args (`fill_args` fills an unrecognised string arg with the mined clause
   tail). The `company` arg is the only one narrowed. Tasks outside the template + a real task the
   LLM path owns (Phase 04 adds replan). `heuristic_plan` is a demo/offline path, not a planner.
3. **`intake_plan` keys on tool names** (`invoice_find_latest`, `erp_post_invoice`). A registry that
   renames them silently falls back to the generic path (no error, just the old heuristic). The
   field mapping (`due`→`due_date`, `file`→`source_file`) is likewise positional-by-name.
4. **`MAX_ATTEMPTS = 2` unchanged**: a failed step is retried once and stays failed (limit 5 above).
5. **LLM path still unexercised** (no `OPENAI_API_KEY` here). `resolve_refs` is a no-op for it: the
   per-step forced tool call already emits concrete args, so LLM plans are unaffected.
6. **`ok is False` is checked strictly** (`{"ok": 0}` is data, not a failure). Tools emit real
   booleans; a tool that signals failure with a truthy non-`False` value still needs a contract fix.
7. **Evidence totals shape changed**: `totals.succeeded` counts only executed steps and
   `totals.cached`/`totals.tools_replayed` are new. Anything downstream reading
   `totals.succeeded` as "succeeded+cached" needs the `+ cached`.

---

# FIX-2 — Phase 04 HELP-1…5 wired into the loop (B2 close-out)

State: **DONE.** All five Phase-04 diffs are applied and exercised. `python3 -m pytest tests/ -q` →
**83 passed, 1 skipped** (was 82 + 1 xfailed; the strict xfail is now a real pass).

## Files changed (my OWN files only)

| File | Fix | What |
|---|---|---|
| `src/runtime/loop.py` | HELP-1/4/5 + HELP-3 | `MAX_ATTEMPTS = 1` + module `POLICY = RetryPolicy()`; `execute()` calls `run_step_with_retry(...)`; one `replan(...)` after the sweep, `run.stage=replan` event, replanned steps executed; `verify()` is now a 3-line lazy delegate to `verifier.checks.verify` (the 100-line predicate copy is gone); `run_task(authorizer=None)` → `Executor(authorizer=…)`; evidence `run` block carries `plan_source` |
| `src/ledger/store.py` | HELP-2 / F3 | `append_step` reads `MAX(attempt)` for `(run_id, step_id)` and bumps a re-used attempt number. A tool failure is data, never an `IntegrityError` |
| `src/ledger/evidence.py` | HELP-3 / F4 | `"plan_source": run.get("plan_source")` in `bundle["run"]` |
| `tests/test_runtime_smoke.py` | HELP-2 + 2 stale premises | `:262` now asserts the bump instead of `pytest.raises(sqlite3.IntegrityError)`; the fatal-failure test lost its retried-once row/count; `import sqlite3` dropped (no longer used) |
| `tests/test_reliability_offline.py` | marker + 1 stale premise | strict `xfail` marker removed (it XPASSes now); the resume test's "service is out for 2 calls" is now "out for all 6" — see Deviations |

Not touched: `src/reliability/*`, `src/verifier/*`, `src/contracts/*`, `src/tools/*`, `src/memory/*`,
`src/policy/*`, `context/*`, `sim_app/*`, `data/*`. No contract or evidence *shape* changed: one new
optional key (`run.plan_source`).

## Verify commands + raw output

### Suite — 04's strict xfail is gone
```
$ python3 -m pytest tests/ -q
........................................................................ [ 85%]
..........s.                                                             [100%]
83 passed, 1 skipped in 5.36s          # was: 82 passed, 1 skipped, 1 xfailed

$ python3 -m pytest tests/test_reliability_offline.py tests/test_runtime_smoke.py -q
..................................................                       [100%]
50 passed in 3.21s                     # was: 49 passed, 1 xfailed

$ python3 -m pytest tests/test_reliability_offline.py -q -k "f3_rerecording" -rx
.                                                                        [100%]
1 passed, 32 deselected in 0.12s
```
(The 1 skip is pre-existing: playwright absent. Wall clock grew ~3s: the loop now really sleeps the
policy's backoff inside tests that go through `run_task`; `run_step_with_retry` itself takes an
injected sleeper in 04's own tests.)

### HELP-4 — verify delegates; the two predicate bugs are gone in the live loop
```
$ ERP_URL=… python3 -m src.runtime.loop --task "find latest invoice from Company X and post it…" \
    --offline --tools auto --runs /tmp/fix2-erp        # run twice: cold, then warm
run 00a874836571 [completed] verdict=pass plan=heuristic   steps: ['succeeded', 'succeeded']  rc=0
run bcb929001f2f [completed] verdict=pass plan=heuristic   steps: ['cached', 'cached']        rc=0

warm run: pass | tools_actually_executed [] | tools_replayed ['erp_post_invoice','invoice_find_latest']
  each_success_has_evidence expected=2 actual=2 passed=True     # was expected=2 actual=0
  audit_trail_complete     expected=3 actual=3 passed=True     # now fails closed per step id
$ curl -s localhost:8903/invoices   ->  {"count": 1, …}   # one row across both runs
```

### HELP-1 — retry+backoff and the replan, live against a downed ERP
```
$ pkill -f sim_app/server.py; ERP_URL=http://127.0.0.1:8903 python3 -m src.runtime.loop \
    --task "find latest invoice from Company X and post it to the ERP" --offline --tools auto --runs /tmp/fix2-down
run 105ee509742a [failed] verdict=fail plan=replan:heuristic
steps: ['cached', 'failed']
real 3.29
rc=1

rows: [('s1', 1, 'succeeded'), ('s1', 2, 'cached'), ('s2', 1, 'failed'), ('s2', 2, 'failed'),
       ('s2', 3, 'failed'), ('s2', 4, 'failed'), ('s2', 5, 'failed'), ('s2', 6, 'failed')]
  log {"attempt": 1, "classify": "retryable", "delay_s": 0.401, "stage": "retry"}
  log {"attempt": 2, "classify": "retryable", "delay_s": 1.123, "stage": "retry"}
  log {"attempts": 3, "stage": "retry_exhausted"}
  log {"attempt": 1, "classify": "retryable", "delay_s": 0.401, "stage": "retry"}     # the replan
  log {"attempt": 2, "classify": "retryable", "delay_s": 1.123, "stage": "retry"}
  log {"attempts": 3, "stage": "retry_exhausted"}
```
Three things in that transcript at once: the sweep retried with growing delays, the replan re-ran the
plan (`plan_source=replan:heuristic`) and `s1` replayed from the ledger as `cached` rather than
re-executing, and the replan's attempts **continued at 4,5,6** — which only exists because of HELP-2.
Before it, `attempt=1` again on `(run, s2)` would have raised `IntegrityError` out of `run_step`.

### HELP-1 note accepted — a 422 now gets 0 attempts (was 1 retry)
Stubbed `erp_post_invoice` → `{"ok": false, "status": 422, "error": "missing required field: amount"}`,
real Phase-02 registry otherwise, through the real `run_task`:
```
status=failed verdict=fail steps=['succeeded','failed'] rc=1
erp_post_invoice called 1 time(s)                       # loop.py MAX_ATTEMPTS=2 used to call it twice
ledger: [('s1', 1, 'succeeded', ''), ('s2', 1, 'failed', 'missing required field: amount')]
failed predicates: ['every_step_resolved', 'criterion:s2']
replan event: [{'detail': 'fatal', 'planned': False, 'reused': [], 'stage': 'replan'}]
```
`classify()` calls it fatal, so the policy spends no retry and the replan refuses it. Fewer duplicate
posts, same red verdict.

### HELP-2 / F3 — a re-used attempt number is data, not a crash
```
$ python3 -m pytest tests/test_runtime_smoke.py -q -k "wal_and_is_append_only"
.                                                                        [100%]
1 passed, 16 deselected in 0.04s
ledger rows after a duplicate (run,step,attempt): [(1, 'succeeded'), (2, 'succeeded')]
```

### HELP-3 — `plan_source` names the planner in the bundle
```
$ python3 -m src.runtime.loop --task demo --offline --tools demo --runs /tmp/fix2-runs
run d3fed34b26bb [completed] verdict=pass plan=heuristic   rc=0
$ python3 -c "print(json.load(open('…/evidence.json'))['run'])"
{"created_at": "2026-10-02T07:45:55.105Z", "goal": "demo", "offline": true,
 "plan_source": "heuristic", "run_id": "d3fed34b26bb", "status": "completed",
 "task": "demo", "updated_at": "2026-10-02T07:45:55.108Z"}
```
A replanned run records `"plan_source": "replan:heuristic"` (seen in the downed-ERP evidence above).

### HELP-5 — a real run can be gated by HITL
`run_task(authorizer=hitl.authorizer)` against a temp queue, then the real CLI:
```
run1 status=blocked verdict=blocked steps=['skipped'] posted=[]
run1 failed predicates: ['criterion:s1']
$ python3 -m src.reliability.hitl --pending --queue /tmp/fix2-gate.jsonl
d90d1100f793  erp_post_invoice  amount=999999.0  erp_post_invoice requires approval
$ python3 -m src.reliability.hitl --approve d90d1100f793 --approver alice --reason "operator signed off" \
    --queue /tmp/fix2-gate.jsonl
d90d1100f793 granted by alice                     rc=0
run2 status=completed verdict=pass steps=['succeeded'] posted=[999999.0]
queue: the `pending` line is intact, a `closed`/`granted` line is appended after it
```
The queue's producer is now inside the loop, which is what HELP-5 was for. Phase 05's CLI can pass
`hitl.authorizer` with no other change; no existing caller changed.

### Resume, unchanged behaviour
```
$ ERP_URL=… python3 -m src.runtime.loop … --runs /tmp/fix2-resume        # ERP down
run 114add2ab526 [failed] verdict=fail plan=replan:heuristic   rc=1
$ python3 sim_app/server.py --port 8903 --db … &                   # service back
$ ERP_URL=… python3 -m src.reliability.checkpoint --runs /tmp/fix2-resume --resume 114add2ab526
resumed 114add2ab526 -> run 24b213a9a1f6 [completed] verdict=pass
inherited: {'s1': 'cached', 's2': 'failed'}
steps:     ['cached', 'succeeded']                                  rc=0
$ curl -s localhost:8903/invoices  ->  ERP count: 1 ['inv-8e41e8ea926c4efb4a4836cb']   # no double post
```

### Regressions still standing
```
$ python3 -m src.runtime.loop --task "" --offline --tools demo --runs /tmp/fix2-empty
run 11359b9467ed [blocked] verdict=blocked plan=heuristic   steps: []   rc=1

$ python3 -c "block socket.connect/create_connection, then run_task('demo', offline, tools='demo')"
rc=0 steps=['succeeded'] elapsed=0.005s, socket blocked for the whole run

$ python3 -m src.reliability.retry "TimeoutError: ERP unreachable at x: timed out"   ->  retryable
$ python3 -m src.reliability.retry "missing required field: amount" 422              ->  fatal
```

## Deviations from the REPORT diffs (deliberate, 3)

1. **`replan()` is only called when something failed.** The diff calls it unconditionally, but
   `replan()` builds its skipped-`Replan` message from `failure.error` — so a clean sweep (no failure)
   would raise `AttributeError: 'NoneType'` inside the loop. One guard, `if failure is not None`.
   A `None`-safe `replan()` is the better fix; it lives in 04's file, so I guarded at my boundary.
2. **`ledger.set_stage(run_id, "execute"/"observe")` around the replanned execution.** Not in the
   diff; without it `runs.stage` still reads `observe` while steps are being executed. 2 lines.
3. **Two stale test premises had to move with the behaviour** (both encoded the pre-wiring loop):
   - `test_runtime_smoke.py::test_failing_tool_…retried_once…`: `"tool exploded on purpose"` is
     unrecognised prose, so `classify()` returns fatal → 1 row, not 2, and `step.failed` counts 2, not
     3. Renamed to `…_is_isolated_never_retried_…`.
   - `test_reliability_offline.py::test_resume_completes_a_run_the_loop_could_not`: its stub was out
     for 2 calls, which the loop now absorbs in-run. Changed to "out for all 6" (3 policy attempts ×
     2 plans) so it still tests what it says: a service the loop cannot fix needs a resume.
   The strict `xfail` marker came off 04's F3 test because it XPASSes — VERIFY §Verify steps
   explicitly allowed updating it, and leaving `strict=True` would have turned the fix into a red suite.

## Remaining limits (honest)

1. **A fully-down service costs 6 attempts, not 3.** The retry policy is per `run_step`, and the replan
   re-runs the plan through the same policy, so `MAX_ATTEMPTS × (1 + MAX_REPLANS) = 6` tool calls and
   ~6s of backoff before the run is graded `fail`. Offline the heuristic planner re-rolls the *same*
   route, so the second plan buys nothing; the transcript says so (`plan_source=replan:heuristic`,
   `reused: []` for a failed step). A budget shared across the run rather than per plan would fix it —
   that is 04's `replan.py`, not mine.
2. **`state.json` still carries the pre-replan plan.** After a replan, `state["plan"]`/`plan_source`/
   `dag` describe the plan that failed; `evidence.json` carries the executed one. Ledger and evidence
   are truthful, the intermediate state file is not.
3. **`adapt()` is now unreachable-by-design** (`MAX_ATTEMPTS = 1` → always `[]`); it survives only to
   keep writing `state["adapt"]` and the observe/adapt stage events. Delete it when 05+ no longer
   reads `state["adapt"]`.
4. **`RetryPolicy` sleeps on the calling thread with the default `time.sleep`**, so the suite pays
   ~3s of real backoff for the loop-level retry tests. Injecting a sleeper through `run_task` would fix
   it; not worth a parameter until someone runs steps in parallel.
5. **`audit_trail_complete` is now fail-closed**, so a run that claims success without a terminal event
   grades `fail` where it used to grade `pass`. No run in this repo is affected; a tool that lies about
   its status now fails the verdict, which is the point.
6. **`run_task(authorizer=…)` gates nothing until a caller passes one.** Phase 05 owns that wiring;
   `limits` in the bundle still reads "no approval channel in Phase 01" because that is still the
   default path.
