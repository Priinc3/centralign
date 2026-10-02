# Batch B1 TEST RESULT — G1 integration (01+02+03)

Ran 2026-10-02 (second run; supersedes the earlier FAIL write-up in this file).
Verdict: **PASS — `invoice intake` E2E works offline, gate blocks as specified, evidence is clean.**

The three blockers from the previous run (planner could not plan the task, `ok:false` recorded as
`succeeded`, empty task green) are fixed and confirmed fixed by execution below. Six new findings,
all minor-to-medium; none blocks G1.

## Env note

| item | value |
|---|---|
| python | 3.14.3 |
| playwright | **absent** (`ModuleNotFoundError: No module named 'playwright'`, `find_spec -> False`) |
| sim_app | `sim-erp` on 127.0.0.1:8901, db `data/sim_erp.db` (persists across runs — see F2) |
| extra sim | second instance on 127.0.0.1:8902, db `/tmp/opencode/sim_scratch.db` (clean, for first-insert proofs) |
| runs/ | warm ledger at start; one extra cold run written to `/tmp/opencode/runs-cold` |

Playwright absent: `browser_open` still cannot be driven end to end. The URL allowlist chokepoint
was exercised directly (section 3) — that path needs no browser.

---

## 0. Setup — PASS

```
$ python3 --version
Python 3.14.3

$ python3 -m pytest tests/test_runtime_smoke.py tests/test_tools_smoke.py tests/test_memory_policy.py -q
......................................s............                      [100%]
50 passed, 1 skipped in 2.21s

$ python3 sim_app/server.py --port 8901 &
$ sleep 1; curl -s localhost:8901/health
{"ok": true, "service": "sim-erp", "db": "/Users/.../centralign/data/sim_erp.db"}
```

## 1. Happy path — PASS

### 1a. Direct tool calls

```
$ ERP_URL=http://127.0.0.1:8901 python3 -c "... invoice_find_latest -> erp_post_invoice x2 ..."
LATEST: INV-X-2024-0912-acme.pdf 4820.00 2024-10-12
POST: {'id': 1, 'idempotency_key': 'inv-8e41e8ea926c4efb4a4836cb', 'vendor': 'ACME SUPPLY CO.',
       'company': 'Company X', 'invoice_number': 'CX-2024-0912', 'amount': '4820.00',
       'currency': 'USD', 'due_date': '2024-10-12', 'source_file': 'INV-X-2024-0912-acme.pdf',
       'created_at': '2026-10-02 06:42:42', 'created': False}
REPLAY same_row: True

$ curl -s localhost:8901/invoices
{"count": 1, "invoices": [{"id": 1, "idempotency_key": "inv-8e41e8ea926c4efb4a4836cb",
  "vendor": "ACME SUPPLY CO.", "company": "Company X", "invoice_number": "CX-2024-0912",
  "amount": "4820.00", "currency": "USD", "due_date": "2024-10-12",
  "source_file": "INV-X-2024-0912-acme.pdf", "created_at": "2026-10-02 06:42:42"}]}
```

`created: False` on the *first* call is dirty-DB state carried over from an earlier session, not a
regression: the row already existed. Proven against a clean DB (F2):

```
$ cp data/sim_erp.db /tmp/opencode/sim_erp.db.bak
$ python3 sim_app/server.py --port 8902 --db /tmp/opencode/sim_scratch.db &
$ curl -s localhost:8902/invoices
{"count": 0, "invoices": []}

$ ERP_URL=http://127.0.0.1:8902 python3 -c "... post x2 ..."
1st created: True | 2nd created: False | same body: True
--- rows ---
rows = 1
```

### 1b. `src.runtime.loop` — PASS (with the replay caveat, F1)

```
$ python3 -m src.runtime.loop --task "find latest invoice from Company X and post it to the ERP" --offline --tools auto
run f9866433d347 [completed] verdict=pass plan=heuristic
dag: s1:invoice_find_latest -> s2:erp_post_invoice
steps: ['cached', 'cached']
evidence: runs/f9866433d347/evidence.json
state:    runs/f9866433d347/state.json
0.10s user 0.02s system 94% cpu 0.126 total
rc=0
```

Planner is fixed: correct two-step order with a real dependency (`find` → `post`), no inverted
chain, no arg laundering. Both steps came back `cached` from the warm ledger, so this particular
run proves the replay path, not the live path. Cold-ledger run against the live sim:

```
$ rm -rf /tmp/opencode/runs-cold
$ ERP_URL=http://127.0.0.1:8902 python3 -m src.runtime.loop --task "find latest invoice from Company X and post it to the ERP" --offline --tools auto --runs /tmp/opencode/runs-cold
run b0de2a6e8ee6 [completed] verdict=pass plan=heuristic
dag: s1:invoice_find_latest -> s2:erp_post_invoice
steps: ['succeeded', 'succeeded']
rc=0

$ ... read evidence
verdict: pass 8/8 predicates passed
step statuses: ['succeeded', 'succeeded']
all passed: True
step statuses: [('s1', 'invoice_find_latest', 'succeeded'), ('s2', 'erp_post_invoice', 'succeeded')]
totals: {'cached': 0, 'events': 10, 'failed': 0, 'skipped': 0, 'steps': 2, 'succeeded': 2,
         'tools_actually_executed': ['erp_post_invoice', 'invoice_find_latest'], 'tools_replayed': []}
```

Live ERP contacted, `tools_actually_executed` lists both tools, 8/8 predicates. F4 from the
previous run (`tools_actually_executed` counting cache hits) is fixed — cold run shows
`tools_replayed: []`, warm run below shows the inverse.

Evidence predicates from the prompt's command:

```
$ cat runs/*/evidence.json | python3 -c "... print verdict + predicates ..."
verdict: {'evidence_ref': 'evidence.json#/verdict', 'predicates': [
  {'name': 'non_empty_goal',        'statement': 'the run was given a non-empty task to accomplish',                    'actual': True,        'passed': True, 'weight': 1},
  {'name': 'plan_has_steps',        'statement': 'the plan contains at least one dispatchable step',                    'actual': 2,           'passed': True, 'weight': 1},
  {'name': 'every_step_resolved',   'statement': 'every planned step ended succeeded, cached or explicitly skipped',     'actual': 0,           'passed': True, 'weight': 1},
  {'name': 'no_silent_skips',       'statement': 'no step was skipped silently (skips are recorded with a reason)',     'actual': 0,           'passed': True, 'weight': 1},
  {'name': 'each_success_has_evidence', 'statement': 'each successful step recorded a result row in the ledger',         'actual': 0,           'passed': True, 'weight': 1},
  {'name': 'audit_trail_complete',  'statement': 'a run.started event plus one terminal event per executed step is on record', 'actual': 3,     'passed': True, 'weight': 1},
  {'name': 'criterion:s1',          'statement': 'a parseable invoice for that company comes back',                     'actual': 'cached',    'passed': True, 'weight': 0},
  {'name': 'criterion:s2',          'statement': 'the ERP accepts the posted invoice',                                'actual': 'cached',    'passed': True, 'weight': 0}],
 'run_id': 'f9866433d347', 'status': 'pass', 'summary': '8/8 predicates passed',
 'verified_at': '2026-10-02T07:09:25.316Z'}
predicates: [('the run was given a non-empty task to ac', True), ('the plan contains at least one dispatcha', True),
             ('every planned step ended succeeded, cach', True), ('no step was skipped silently (skips are ', True),
             ('each successful step recorded a result r', True), ('a run.started event plus one terminal ev', True),
             ('a parseable invoice for that company com', True), ('the ERP accepts the posted invoice', True)]
```

## 2. Top-3 edges — 3 PASS

**E1 empty task — PASS** (was FAIL/F3)

```
$ python3 -m src.runtime.loop --task "" --offline --tools demo
run d68d74d082ee [blocked] verdict=blocked plan=heuristic
dag: (no steps)
steps: []
rc=1

$ python3 -c "... read runs/d68d74d082ee/evidence.json ..."
status: blocked | No task given
summary_text: None
FAILED PRED: non_empty_goal | the run was given a non-empty task to accomplish | actual: False | detail: No task given
FAILED PRED: plan_has_steps | the plan contains at least one dispatchable step | actual: 0 | detail: None
```

No crash, `rc=1`, verdict `blocked`, plain words ("No task given"), and the empty goal is now an
explicit failing predicate instead of a green run.

**E2 double-submit — PASS**

```
1st created: True | 2nd created: False | same body: True
rows = 1
```

Also confirmed at the executor layer: a successful step is replayed without re-invoking the tool.

```
success then replay in same run: succeeded -> cached | tool actually called again: 1
```

**E3 offline no-key — PASS**

```
$ time env -u OPENAI_API_KEY python3 -m src.runtime.loop --task "demo" --offline --tools demo
run 3871c33386ec [completed] verdict=pass plan=heuristic
dag: s1:echo_note
steps: ['cached']
0.09s user 0.03s system 74% cpu 0.153 total
rc=0

$ ... --json
json keys: ['dag', 'evidence', 'plan_source', 'registry', 'run_dir', 'run_id', 'state', 'status', 'steps', 'verdict']
plan_source: heuristic | status: completed
$ python3 -c "... read runs/3871c33386ec/evidence.json ..."
plan_source: None | mode: None | verdict: pass
totals: {'cached': 1, 'events': 7, 'failed': 0, 'skipped': 0, 'steps': 1, 'succeeded': 0,
         'tools_actually_executed': [], 'tools_replayed': ['echo_note']}
```

`plan_source=heuristic`, `rc=0`, 0.153s (<2s). Note `plan_source` is on stdout only, not in
`evidence.json` (F4).

## 3. Security probes — PASS (all hold)

```
$ python3 -m src.policy.gate --tool erp.post --amount 999999 ; echo exit=$?
approve
exit=0
$ python3 -m src.policy.gate --tool erp.post --amount 10 ; echo exit=$?
allow
exit=0
$ python3 -m src.policy.gate --domain evil.com ; echo exit=$?
deny
exit=2
```

```
$ python3 -c "... ALLOWLIST=localhost,example.com; check_url each ..."
http://localhost:8901/portal -> ALLOW http://localhost:8901/portal
https://example.com/x -> ALLOW https://example.com/x
http://evil.com -> DENY host not on ALLOWLIST=localhost,example.com: evil.com
http://example.com.evil.com -> DENY host not on ALLOWLIST=localhost,example.com: example.com.evil.com
file:///etc/passwd -> DENY only http(s) URLs allowed: 'file:///etc/passwd'
javascript:alert(1) -> DENY only http(s) URLs allowed: 'javascript:alert(1)'
```

Suffix-match is correct: `example.com.evil.com` denied.

```
$ python3 -c "... execute('files_read', path='../../etc/passwd') ..."
{'ok': False, 'tool': 'files_read', 'risk': 'read',
 'error': "ValueError: path escapes data/ sandbox: '../../etc/passwd'"}
rc=0
```

Denied, no file content leaked. It returns an `ok:False` envelope rather than raising, so the
prompt's `except` branch never prints — the prompt's expectation is wrong, the behaviour is right
(envelope is this codebase's failure convention, and the executor now treats it as `failed`).

```
$ grep -rniE "sk-[a-zA-Z0-9]{10,}|password *= *['\"][^'\"]+['\"]|bearer " src/ sim_app/ context/ || echo "NO SECRETS"
src/contracts/events.py:49:    """Mask secret-looking keys and inline `Bearer <tok>` / `sk-...` values, recursively."""
src/contracts/events.py:60:            value = re.sub(r"(?i)bearer\s+\S+", f"Bearer {REDACTED}", value)
Binary file src/contracts/__pycache__/events.cpython-314.pyc matches
```

Both hits are the redactor's own docstring and regex. No real secret in the tree.

```
$ python3 -c "... 'sk-' in latest evidence.json ..."
EVIDENCE CLEAN
$ grep -rlE "sk-[a-zA-Z0-9]{10,}" runs/ 2>/dev/null || echo "no sk- in runs/"
no sk- in runs/
$ python3 -c "... ToolManifest name='erp.post' ..."
DOTTED-NAME OK: erp.post -> erp_post
```

Added positive control — "no leak" is only meaningful if the redactor fires at all:

```
$ python3 -c "from src.contracts.events import redact; print(redact({...}))"
{'tool': 'erp.post', 'headers': {'Authorization': '[REDACTED]'}, 'note': 'key [REDACTED] used',
 'n': {'api_key': '[REDACTED]'}}
```

Bearer header, inline `sk-…` in free text, and secret-looking key name all masked.

## 4. Cross-phase integration — PASS

```
$ python3 -c "... registry / load_context / decide / Store / recall ..."
tools: ['browser_open', 'erp_post_invoice', 'files_list', 'files_read', 'invoice_find_latest', 'invoice_parse']
gate erp.post/10: allow
gate browser evil: deny
recall: [{'id': 1, 'category': 'acme_payment_terms', 'key': 'terms',
          'value': 'net 30 billing contact [REDACTED:email]', 'source': '', 'redacted': 1,
          'created_at': '2026-10-02T07:11:48+00:00', 'score': -2.3749999999999997e-06}]
```

Library gate agrees with the CLI gate; PII redaction fires at the memory layer (`a@b.com` →
`[REDACTED:email]`).

**`ok:false must NOT look green` — PASS (the 02 HELP holds)**

The prompt's probe is still wrong (`run_step` takes `(step, seq)` and the ad-hoc `type('S',...)`
object has none of `Step`'s required fields):

```
$ ... exactly as written in the prompt ...
TypeError: Executor.run_step() missing 1 required positional argument: 'seq'
```

Corrected with the real `Step` model and `fn(**args)`:

```
$ python3 -c "... Executor(led, rid, {'t': m}, {'t': lambda **a: {'ok': False, 'status': 422, 'body': 'bad'}}) ..."
ok:false -> failed (must be failed, not succeeded)
error: tool returned ok:false (status=422)
attempt1: failed | ok: False | resolved: False
attempt2 (replay of a failure): failed (must not be cached/succeeded)
ledger rows: [('s1', 1, 'failed'), ('s1', 2, 'failed')]
```

An `ok:false` payload is recorded `failed`, `StepResult.ok` is False, it is not `resolved`, and a
second attempt re-executes rather than replaying a poisoned row. The laundering chain from the
previous run is closed.

---

## Findings

### F1 — MEDIUM: `verdict=pass` can be produced with zero live tool calls
`src/ledger/store.py:154` `find_by_idem` searches **any** run, so once a step has succeeded once,
every later run of the same task reports `cached` and never touches the ERP. Section 1's headline
command passed on a warm ledger with `steps: ['cached','cached']` and
`tools_actually_executed: []`. Replay is correct behaviour for idempotent money-path calls, but the
evidence bundle gives a reader no way to tell a replayed pass from an executed pass except by
reading `totals`. Cold run (`--runs <empty dir>`) passes with `succeeded/succeeded` and
`tools_replayed: []`. Suggest: the prompt's section 1 should use a fresh `--runs` dir, or the CLI
should print `replayed=N` next to `verdict=`.

### F2 — MEDIUM: sim DB persists, so section 1 is not reproducible on a dirty database
`data/sim_erp.db` carries rows between sessions, so the first `erp_post_invoice` returned
`created: False` and `REPLAY same_row: True` — indistinguishable from "the first insert never
created anything". Clean-DB proof required a second sim instance (`--db /tmp/...`). Suggest: the
test doc start the sim with a scratch `--db`, or the sim expose a reset endpoint.

### F3 — LOW: re-recording the same `(run_id, step_id, attempt)` escapes as an unhandled crash
`src/ledger/store.py:47` `UNIQUE (run_id, step_id, attempt)` + `src/runtime/executor.py:190`
`_record` → `append_step` means recording a step twice with the same attempt raises
`sqlite3.IntegrityError` out of `run_step`, including from the error-recording path
(`src/runtime/executor.py:163`). That breaks the file's own invariant that "a tool failure is data,
not a crash". Not reachable through `src.runtime.loop` today (`src/runtime/loop.py:353` increments
`attempt` before retrying), so it is latent for any future repair/replay caller.

### F4 — LOW: `plan_source` is not in the evidence bundle
`evidence.json`'s `run` block has only `created_at/goal/offline/run_id/status/task/updated_at`;
E3's `plan_source=heuristic` is only observable via `--json` on stdout. Cheap fix: add it to the
`run` block so the artifact is self-describing.

### F5 — TEST-DOC: the section-4 `Executor` probe is still broken
`ex.run_step(...)` needs `(step, seq)` and a real `src.runtime.planner.Step`; the `type('S', (), {...})`
stand-in lacks `intent` and `success_criterion`. Six of the prompt's probes were broken in the
previous run; this one remains and fails before reaching the assertion it exists to make.

### F6 — TEST-DOC: `files_read` traversal returns an envelope, not an exception
The prompt expects a raise (`except` branch prints `TRAVERSAL BLOCKED`); the tool returns
`{'ok': False, ..., 'error': "ValueError: path escapes data/ sandbox: ..."}`. Security holds, the
assertion shape is wrong.

## Scorecard

| section | result |
|---|---|
| 0 setup / unit tests | PASS (50 passed, 1 skipped) |
| 1 happy path — direct tools | PASS (clean-DB proof) |
| 1 happy path — runtime loop | PASS (cold ledger; warm ledger replays — F1) |
| 2 E1 empty task | PASS (blocked, rc=1, plain words) |
| 2 E2 double-submit | PASS (rows=1, 2nd created=False) |
| 2 E3 offline no-key | PASS (heuristic, rc=0, 0.153s) |
| 3 security (6 probes) | PASS (+ redaction positive control) |
| 4 cross-phase integration | PASS (`ok:false` -> failed, gate, recall/redaction) |
| **G1 invoice intake E2E offline** | **PASS** |

Sim servers: `pkill -f "sim_app/server.py"` run after the suite.