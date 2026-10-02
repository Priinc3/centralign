# FIX-1 — Phase 01 runtime (owns B1 blockers F1/F2/F3/F4)

Scope locked: `src/runtime/*`, `src/ledger/*` only. DO NOT touch `src/tools/*`, `src/memory/*`, `context/*`, `src/contracts/*` (frozen — if contract must change, post HELP, wait). Update `prompts/phase-01-runtime/REPORT.md` (append FIX-1 section with cmds+output).

## P0 — F2 executor launders {ok:False} → succeeded (🔴)
Problem: `src/runtime/executor.py:99-101` treats any non-raising return as success; `store.py:156` caches it; `StepResult.ok` True for cached → ERP 422 reads green, replayed green.
Fix: after tool return, if `isinstance(result,dict) and result.get("ok") is False` → record `failed` with `error=result.get("error") or status`, do NOT cache as succeeded (store failed row; replay of failed re-executes or stays failed, never `cached`+ok). `StepResult.ok` True only when status==`succeeded` AND payload ok≠False.
Verify: corrected probe with real signature `Executor(ledger,run_id,manifests,callables)` + `lambda **a: {'ok':False,...}` → `failed`; then `python3 -m src.runtime.loop --task "find latest invoice from Company X and post it to the ERP" --offline --tools auto` shows s1 `failed` (not succeeded) when ERP 422.

## P0 — F1 heuristic cannot plan invoice intake (🟠)
Problem: `planner.py:137 _AFTER_RE` greedy; `:169 fill_args` fills every key with `values[text]`; `:201-212` alphabetical; `:224` sequential chain.
Fix (minimal, narrow-genuine): arg-aware fill — `company`←`Company X|Company Y` regex else omit; `dir`←`data/seed/invoices` default (never task text); `pattern`←`*.pdf`; never fill `amount/vendor/due_date/invoice_number` from task text (leave for find-output; if LLM path, per-step call fills). Order: reads (`invoice_find_latest`,`invoice_parse`,`files_*`,`browser_open`) before writes (`erp_post_invoice`); chain `depends_on` find→post. If task mentions invoice+Company X+post/ERP, emit 2-step template find→post.
Verify: `python3 -m src.runtime.loop --task "find latest invoice from Company X and post it to the ERP" --offline --tools auto` → dag `s1:invoice_find_latest -> s2:erp_post_invoice`, steps `['succeeded','succeeded']`, verdict pass 7/7; `curl -s localhost:8901/invoices` count 1.

## P1 — F3 empty task green (🟠)
Problem: `planner.py:207-211` fallback runs lowest-risk tool on `""`.
Fix: if `task.strip()==""` → empty plan, verdict `blocked` (or fail) with predicate `non-empty goal: False`, plain message "No task given".
Verify: `python3 -m src.runtime.loop --task "" --offline --tools demo` → verdict blocked/fail, rc≠0 or explicit blocked, not pass.

## P2 — F4 cached counted as executed (🟡)
Problem: `evidence.py:68` counts `cached` in `tools_actually_executed`.
Fix: count only `succeeded` with actual execution in this run (exclude `cached`), or rename field to `tools_recorded`.
Verify: rerun same task twice → second run `tools_actually_executed: []` (or no false claim).

## Report
Append to REPORT.md: files changed, each Verify cmd + raw output, remaining limits.
Post INFO in COMM, set STATUS 01→DONE when green.
