# G1 comm

## 01 11:38 — started; writing frozen contracts (ToolManifest/Event/Verdict) then runtime loop [INFO]
## 01 11:44 — contracts FROZEN. ToolManifest fields: name (dots ok), description, parameters (accepts `input_schema` alias), risk, idempotent, requires_approval, side_effect_free; openai_tool() emits strict:true [DECISION]
## 01 11:46 — dots handled at MY API boundary (api_name() dots→underscore), so your dotted names need no rename; optional args become nullable+required automatically for strict mode [DECISION]
## 01 11:48 — HELP: src/tools/__init__.py exports `manifests`, registry now has `registry()`; import fails, my loop falls back to the built-in demo tool (loud warning) [HELP]
## 01 11:50 — runtime loop + ledger + evidence DONE offline: 13 tests pass, `--task demo --offline` writes runs/<id>/evidence.json. 03: dots request answered, no change needed on your side [INFO]
## 01 11:56 — INFO 02: files.list run() needs args["action"]="list"; with dir/pattern only it raises KeyError 'path'. My loop records it as a failed step (verdict=fail), not silently [INFO]
## 01 11:57 — offline demo is now sibling-independent: `python -m src.runtime.loop --task demo --offline --tools demo` (auto = your registry when importable). Registry API I call: registry()/load() + callables(), else manifests()+execute() [DECISION]

## 02 12:05 — contracts consumed: manifests use `parameters`, ids underscore (NAME_RE), all props required. Dotted ids still resolve [INFO]

## 02 12:05 — DECISION 01: tool ids are `files_list,files_read,invoice_parse,invoice_find_latest,erp_post_invoice,browser_open`; `resolve()` maps `erp.post`→erp_post_invoice for 03's gate [DECISION]

## 02 12:06 — 01: `registry()`+`callables()` are exported, so your load_registry() preferred path works — `manifests()` not needed, verified via your loop [INFO]

## 02 12:06 — HELP 01/04: Executor records a step `succeeded` when a tool returns `{ok:false}` (e.g. 422). Treat `result.ok is False` as failed, else a failed ERP post looks green [HELP]

## 02 12:06 — HELP 01: offline heuristic planner fills every string prop with the whole task, so `dir` gets the task text. Sanitize by arg name in planner [HELP]

## 01 12:4x — FIX-1 DONE: F2 (ok:false no longer green), F1 (offline invoice intake works), F3 (empty task blocked), F4 [INFO]

Tool contract unchanged, nothing needed from 02/03. What a tool may return is now load-bearing in 01:
- **A dict result with `ok is False` is a FAILED step**, not a result. `StepResult.ok` is only true for
  `status=="succeeded"` with a non-`ok:false` payload; `StepResult.resolved` (succeeded or cached,
  payload not `ok:false`) is what a dependent step may rely on. If you add a tool, return `{"ok": false,
  "error": "..."}` for a failure — do **not** raise *and* do not return ok:false without an error
  message (the message becomes the step's `error`). Raise for programmer errors only.
- **A step may carry `{{s1.field.path}}` arg values**, resolved by the executor from the dependency's
  recorded result before the manifest schema check; an unresolvable ref fails the step rather than
  reaching the tool. 01's offline planner uses it for `erp_post_invoice` (all payload values come from
  `invoice_find_latest.latest`). Nothing in your manifests changes; optional.
- **`erp_post_invoice` args**: `base_url` and `idempotency_key` must keep a working default when the
  value is empty ("" → `$ERP_URL`, payload hash). 01 relies on that instead of mining the task text.
- `manifest_registry.execute()`'s `wrap()` in `src/runtime/loop.py` (the `manifests()+execute()`
  fallback path) raising on `ok:false` is now redundant but harmless; `registry()+callables()` is what
  actually runs.

## 01 13:5x — FIX-2 DONE: 04's HELP-1…5 wired into the loop (retry+replan, verify delegation, HITL gate, F3 attempt bump, plan_source in evidence) [INFO]

Behaviour changes that touch your files (04 owns `reliability/*`, 05 owns the CLI):

- **The loop retries per policy now, not once.** A transient failure (timeout, connection refused,
  408/425/429/5xx) earns up to 3 attempts with growing seeded backoff; everything unrecognised is
  **fatal — one attempt, no retry, no replan**. A `422` therefore gets **0 retries** (it used to get 1).
  If your tool words a retryable fault outside `RETRYABLE_TEXT`, say so in the message text
  ("connection refused" / "timed out" / "service unavailable") or it will be graded fatal.
- **A transient failure also triggers one replan**, so a fully-down service costs 6 calls
  (`3 attempts × (1 plan + 1 replan)`) before the run grades `fail`. Offline the heuristic planner
  re-rolls the same route, so the replan mostly re-proves the failure; `plan_source` becomes
  `replan:heuristic` in the evidence bundle when it happens.
- **`run_task` takes `authorizer=`** (`Callable[[ToolManifest, dict], str] -> allow|approve|deny`).
  05: pass `hitl.authorizer` from the CLI and the approval queue gets a real producer inside the loop —
  proven: queued → `blocked`, `--approve` → the next run posts. No existing caller changed.
- **The ledger never re-uses an attempt number.** `append_step` bumps a duplicate `(run, step, attempt)`
  instead of raising `IntegrityError`, so a replan/retry that re-runs a step records attempts 4,5,6…
  as data. Anything that was catching `sqlite3.IntegrityError` around a step record must stop
  (04's `test_run_id_reuse_does_not_resume_in_place` still relies on it for `runs`, which is unchanged).
- **`loop.verify` is now `verifier.checks.verify`** (one copy of the predicates, not two). Predicate
  names, `blocked` semantics and the evidence shape are unchanged; `each_success_has_evidence` now
  counts cached steps correctly and `audit_trail_complete` fails closed per step id. The inline copy is
  deleted — do not patch predicates in `loop.py` any more.
- **`evidence.json:run` gains `plan_source`** (`"heuristic"` / `"llm"` / `"replan:heuristic"`). One new
  optional key; no other shape change.
- 04's two test premises moved with the behaviour (a fatal stub is no longer retried; the resume test's
  stub is now out for all 6 attempts), and its strict `xfail` F3 marker is gone — it passes now.
