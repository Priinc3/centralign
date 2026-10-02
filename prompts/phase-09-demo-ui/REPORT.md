# REPORT — Phase 09 demo UI (NORMAL, evaluator-visible)

Three new files, nothing else touched. The engine, the ledger, HITL and `src/cli/main.py` are
unmodified; the page reuses them rather than re-implementing the demo.

| file | lines | what |
|---|---|---|
| `src/ui/app.py` | 346 | stdlib `http.server` + the demo session (run → approval → resume), sim ERP lifecycle |
| `src/ui/index.html` | 252 | the page: Run button, step list, approval card, verdict, evidence, ERP row; vanilla JS, 500ms poll |
| `tests/test_ui_offline.py` | 181 | 6 tests over HTTP — no browser, no API key |

```
$ python3 -m src.ui.app --port 0
fresh       /tmp/centralign-ui/sim.db  (empty ERP db)
fresh       /tmp/centralign-ui/runs  (run root)
fresh       /tmp/centralign-ui/gate.jsonl  (approval queue)
sim ERP     http://127.0.0.1:51690  db=/tmp/centralign-ui/sim.db  (started for this page, stopped with it)

CentrAlign demo UI  http://127.0.0.1:51694
task    find latest invoice from Company X and post it to the ERP
planner heuristic (offline, no key needed)
scratch /tmp/centralign-ui  (wiped on start; rerun for a cold pass 8/8)
ctrl-c stops the page and the sim ERP
```

```
$ GET /            -> 200  11682 bytes  0.001141s        # first paint, 1.1ms
$ POST /api/run     -> 202
$ POST /api/approve -> 200
$ POST /api/run     -> 202   (second click)
$ GET /api/state    -> pass 8/8 | ERP rows: 1 | replayed: 2 | planner: heuristic
```

The full step-by-step transcript of that session (from `/api/state` at each phase):

```
  phase running   | banner: working…                    | erp rows: 0
  phase awaiting  | banner: blocked / 7/8 predicates passed | pending: 1 (erp_post_invoice $4,820.00)
  s1 succeeded  -- CX-2024-0912  $4,820.00 USD  due 2024-10-12
  s2 skipped    -- not posted — waiting for a human to approve it (the card beside this list)
  phase done     | banner: pass 8/8                     | erp rows: 1 | replayed: 1   (cold)
  phase done     | banner: pass 8/8                     | erp rows: 1 | replayed: 2   (second Run)
```

Every BUILD criterion holds: cold Run → Approve → `pass 8/8`, ERP count 1, evidence visible; the
second Run shows `replayed=2` and posts nothing new.

## Verification

```
$ python3 -m pytest tests/test_ui_offline.py -q
......                                                                   [100%]
6 passed in 4.00s

$ python3 -m pytest tests/ -q
133 passed, 1 skipped in 11.27s        # was 127 + 1 skipped

$ python3 -m src.security.scan
scanning 6 trees for credentials  … none
allowlisted canaries  2  (tests/, marker-checked: the line must still say why)
guards  deny unknown tool · deny evil host + suffix trick · deny /etc traversal · redactor masks a live secret

findings: 0  → safe to publish
rc=0
```

The page leaks nothing: it never reads a key, and every `/api/state` payload goes through
`redact()` on the way out (same helper the ledger uses).

**No key required** — verified with every key unset:

```
$ env -u OPENAI_API_KEY -u GEMINI_API_KEY -u GEMINI_API_KEY_2 -u GEMINI_API_KEY_3 \
      -u ANTHROPIC_API_KEY -u GOOGLE_API_KEY bash demo/run.sh
… run -> 202 ; approve -> 200
no-key run: pass 8/8 | rows: 1 | replayed: 1
```

Localhost only: `serve()` binds `127.0.0.1` and `--host` refuses anything else
(`test_the_page_cannot_be_bound_off_localhost`), and the test asserts the socket's own address.

## Screenshot (description — the PNGs are in `/tmp`, not in the tree)

Two headless captures, 1180×820, taken with a locally cached Chromium headless shell (used only to
photograph the page — the page itself needs no browser tooling, and the test drives it over HTTP):

- **`/tmp/ui-awaiting.png`** — dark single page. Title, subtitle, blue `Run again (run 2)` button,
  the task in a mono strip, an amber banner `blocked / 7/8 predicates passed`. Left card: `STEPS (2)`
  with a green ✓ `s1 · invoice_find_latest` / `CX-2024-0912 $4,820.00 USD due 2024-10-12` and a
  yellow ⏸ `s2 · erp_post_invoice` / `not posted — waiting for a human to approve it`, then
  `ERP ROW: 0 rows in the ERP`. Right card: the amber approval card naming `erp_post_invoice ·
  $4,820.00`, the request id, a name box and a green **Approve** button, plus the evidence panel
  (file, events 10, `invoice_find_latest` executed, none replayed, 7/8 predicates).
- **`/tmp/ui-pass.png`** — same page after approving and clicking Run twice: green banner
  `pass 8/8 replayed=2`, both steps blue ↻ reading `replayed from the ledger (not called again) · …`,
  `ERP ROW: 1 row` with id / vendor / invoice / amount / due / source file, and evidence showing
  `tools executed: none`, `tools replayed: erp_post_invoice, invoice_find_latest`, `8/8 passed`.

## The demo with a real key (`--llm`)

`--llm` mirrors the CLI's flag: plan with the LLM when a key is in the environment, degrade to the
deterministic heuristic otherwise. Run with the Gemini key exported (never written to a file):

```
$ export GEMINI_API_KEY='…' && python3 -m src.cli.main demo --llm --approve demo-operator
run 1  2b210920064b
  ✓ s1  invoice_find_latest    CX-2024-0912  $4,820.00 USD  due 2024-10-12
  ⏸ s2  erp_post_invoice       not posted — waiting for a human to approve it (queued below)
  ✓ 511862b21882  erp_post_invoice $4,820.00  approved by demo-operator
run 2  continuing 2b210920064b
  ↻ s1  invoice_find_latest    CX-2024-0912  $4,820.00 USD  due 2024-10-12
  ✓ s2  erp_post_invoice       ERP row #1 created

verdict: pass 8/8   replayed=1   plan: heuristic(fallback: PlannerError: LLM returned no tool call)
ERP count: 1
```

**The key works; the plan schema does not survive it.** Three probes, in the same shell:

| probe | result |
|---|---|
| manifest-level forced tool call (what `_step_args` does) | ✅ `finish_reason: tool_calls`, real args `{"pattern":"*","dir":"seed/invoices","company":"Company X"}` |
| `submit_plan` strict schema (what `llm_plan` does first) | ❌ `finish_reason: function_call_filter: MALFORMED_FUNCTION_CALL`, no tool call, empty content |
| same schema with `$defs` inlined, and with the pinned `args` object loosened | ❌ identical — it is the schema shape, not the `$ref`s |
| a later call | ⚠️ `429 RESOURCE_EXHAUSTED` on the free tier, key cooled 60s, next run says `cooling down: gemini#1` |

So the transport, the multi-key router and the key are fine; **Gemini's function-call filter rejects
`src/runtime/planner.py:_plan_submit_tool()`'s strict schema** (the pinned empty `args` object with
`required: []` is the prime suspect — Gemini's own validator rejected a sibling variant with
`schema at properties.steps.items requires unspecified property 'args'`). `make_plan` then degrades
exactly as designed, so the demo still passes 8/8 — the fallback is a feature, not a crash.

**Not fixed here on purpose:** `planner.py` is frozen for this phase (BUILD: engine read-only), and
a one-line schema change to the LLM planner belongs to whoever owns Phase 02/04 — it is a
cross-cutting change with its own test surface, not a Phase 09 edit. One-line repro:

```
python3 -m src.ui.app --llm     # with GEMINI_API_KEY exported
```

## Notes / limits

- **Scratch is `/tmp/centralign-ui`, wiped at startup** (`cli.fresh`, so it refuses non-scratch
  paths). Wiping is deliberate: a leftover ERP row or a warm ledger makes the first Run ambiguous,
  and a stale *grant* in the queue would skip the approval card entirely. `--scratch` points it
  elsewhere. It does not touch the CLI demo's `/tmp/centralign-demo`.
- **The Approve button closes one named request.** `hitl.decide` refuses an unknown or already-closed
  id, so a stale card cannot double-release anything; a blank name is recorded as the signed-in user
  (`cli.approver_name()`), the same rule the CLI prompt follows — never unowned. `POST /api/run`
  while a run is in flight is `409`, not a second concurrent run.
- **What the page is not:** no websocket/SSE (it polls `/api/state` at 500ms, which is what the CLI's
  follower does over the ledger), no auth (localhost only, like every other server here), no
  multi-run history — one cycle at a time, `Run again` starts a new one on the same ledger.
- **`src/cli/main.py` coordination (BUILD asked for this):** I depend only on its **public**
  helpers — `DEFAULT_TASK`, `start_sim`, `wait_sim`, `free_port`, `fresh`, `head`, `say`, `money`,
  `approver_name`. No private name is imported, so 05/FIX-2 landing in that file cannot break the
  page. Nothing in `src/cli/main.py` was edited.
- README is untouched, as BUILD asked (numbers to be refreshed in the 08-style pass). The one number
  that moved: the suite is now **133 passed, 1 skipped** (was 127 + 1 skipped) — README line 52/223/232
  still says 127 and will need the same edit the 08 pass did.
- Video: the optional 20s UI beat can be re-recorded from this session — cold Run, approve, second
  Run showing `replayed=2` is the whole story in three clicks.