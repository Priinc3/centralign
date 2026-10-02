# REPORT — Phase 07 user acceptance (NORMAL)

## Files changed

| file | status | what |
|---|---|---|
| `src/llm/router.py` | **new** (231 lines) | multi-key LLM router: env key discovery, round-robin, cooldown, failover, redaction |
| `tests/test_llm_router_keys.py` | **new** (12 tests) | rotation order, 429 failover, no-retry on 401, 400 triage, key redaction — all offline |
| `scripts/browser_check.py` | **new** (140 lines) | Playwright sync check of the sim portal on a scratch sim; allowlist-negative before any launch |
| `docs/USER-TEST.md` | **new** | 13-step follow-along runbook + API/key table + pre-submit checklist |
| `src/runtime/planner.py` | **edited, 12 lines** | *the* granted exception: `_openai_client()` deleted, `llm_plan` now builds its client from `src.llm.router.router()`. Nothing else in the file touched. |

Untouched as instructed: `demo/*`, `README.md`, `SUBMISSION.md`, all REPORTs/VERIFYs,
`prompts/final-TEST-RESULT.md`, `src/security/scan.py`, every other `src/` module.

No new dependency. `playwright` stays optional and is imported lazily.

---

## Commands + raw output

### Criteria 1 — `python3 scripts/browser_check.py` → PASS with playwright, clean SKIP without

```
$ python3 scripts/browser_check.py; echo "rc=$?"
CentrAlign browser check · localhost only · scratch /tmp/centralign-browser
  ✓ allowlist              evil.com, the suffix trick and file:// refused, no browser launched

SKIP: playwright is not installed, so there is no browser to drive. Nothing is wrong with CentrAlign — every other claim in README.md runs offline without it.
      to run this check anyway:  pip install playwright && python3 -m playwright install chromium
rc=0
```

```
$ /tmp/opencode/pwvenv/bin/python scripts/browser_check.py; echo "rc=$?"      # venv + playwright + chromium
CentrAlign browser check · localhost only · scratch /tmp/centralign-browser
  ✓ allowlist              evil.com, the suffix trick and file:// refused, no browser launched

sim ERP   http://127.0.0.1:64853  db=/tmp/centralign-browser/sim.db  (started for this check, stopped when it ends)
  ✓ portal loads           HTTP 200, title 'Acme portal — inbox'
  ✓ 3 invoices listed      2024-0703-acme.pdf — 993 bytes, 2024-0912-acme.pdf — 1156 bytes, 2024-0805-other.txt — 201 bytes
  ✓ screenshot             /tmp/centralign-browser/portal.png

PASS: the portal rendered in a real browser, the allowlist refused evil.com without launching one, and the screenshot is on disk.
rc=0
real 0m1.747s      # budget was <30s
```

Screenshot read back and inspected: a real headless-chromium render of
`Acme portal — inbox` with all three seeded files. System python has no `playwright` (Homebrew
PEP 668), so the PASS path was run from a venv with `playwright` + `chromium` installed
(`/tmp/opencode/pwvenv`) — no repo file was changed to achieve it.

### Criteria 2 — runbook §1–12 on a cold scratch

Every expected-output block in `docs/USER-TEST.md` was transcribed from a real run, not written
from memory. Re-verified end to end on a fresh `/tmp/uat` after the last code change:

```
$ python3 -m src.cli.main doctor | tail -2 ; python3 -m src.cli.main doctor >/dev/null; echo "exit code: $?"
network     ok     not needed: no API key, no internet — only 127.0.0.1 is contacted

ready: the offline demo runs (python3 -m src.cli.main demo)
exit code: 0

$ bash demo/run.sh /tmp/uat | tail -8
run 2  continuing bd3b22727748  (new run id: the ledger is append-only)
  ↻ s1  invoice_find_latest    CX-2024-0912  $4,820.00 USD  due 2024-10-12
  ✓ s2  erp_post_invoice       ERP row #1 created

verdict: pass 8/8   replayed=1   plan: heuristic   run: 3bfa7de6cacf
ERP count: 1
evidence: /tmp/uat/runs/3bfa7de6cacf/evidence.json

$ bash demo/run.sh /tmp/uat --append | tail -6
  ↻ s2  erp_post_invoice       ERP row #1 created

verdict: pass 8/8   replayed=2   plan: heuristic   run: 9ae357b7aadd
ERP count: 1  (unchanged: nothing was double-posted)
```

Also verified, each from the runbook:

```
step 4  $ python3 -m src.cli.main run --task ""      → verdict: blocked / No task given   rc=1
step 5  $ ERP_URL=http://127.0.0.1:9 … --approve alice
        → verdict: fail 6/8   plan: replan:heuristic   rc=1        (6 failed rows, no pass claimed)
step 6  $ python3 -m src.reliability.checkpoint --runs /tmp/uat-b/runs --resume <id>
        → resumed <id> -> run <new> [failed] verdict=fail
          inherited: {'s1': 'succeeded', 's2': 'skipped'}   steps: ['cached', 'failed']
step 7  $ python3 -m src.reliability.hitl --approve <rid> --approver alice   → 9292a537493d granted by alice
        $ … --resume <id>  → [completed] verdict=pass, steps: ['cached','succeeded']
        $ curl …/invoices  → {"count": 1, … "CX-2024-0912" …}
        $ … --approve <same rid> --approver mallory → refused: request … is already 'closed'   rc=2
step 11 evidence snippet → executed [] / replayed ['erp_post_invoice','invoice_find_latest'],
                           8 PASS predicates   (cold run of step 2 for contrast:
                           executed ['erp_post_invoice'] / replayed ['invoice_find_latest'])
```

### Criteria 3 — the suite stays green

```
$ python3 -m pytest tests/ -q
127 passed, 1 skipped in 7.35s          # was 115 passed, 1 skipped; +12 router tests

$ python3 -m src.security.scan
findings: 0  → safe to publish
```

### The router, against the real Gemini endpoint

Not mocked, not hypothetical — run with the owner's key exported in the shell only (never
written to a file, never committed). A deliberately invalid key was placed **first** so the
failover had to happen for real:

```
$ GEMINI_API_KEY=<invalid>  GEMINI_API_KEY_2=<real>  … make_plan(task, registry(), offline=False)
EVENT: {'key': 'gemini#1', 'attempt': 1, 'outcome': 'cooldown', 'status': 400,
        'reason': "Error code: 400 - [{'error': {'code': 400, 'message': 'Please pass a v…"}
EVENT: {'key': 'gemini#2', 'attempt': 2, 'outcome': 'ok'}
```

```
$ … --approve alice  (live 401/429/400 paths exercised)
429 → {'outcome': 'cooldown', 'status': 429, 'reason': 'Error code: 429 - … You exceeded …'}
     then: LlmError: no usable LLM key: set GEMINI_API_KEY or OPENAI_API_KEY in the environment (cooling down: gemini#1)
```

Rotation, cooldown, failover and redaction are therefore proven live, not only in tests.

---

## Findings

**F1 — 🔴 the owner pasted a live Gemini API key into the chat.** It is now in the transcript
in plain text and must be treated as exposed: rotate it in Google AI Studio. It was used from
the environment only and written to no file; `python3 -m src.security.scan` proves the tree is
clean. Nothing else in this repo needs changing, but the disclosure is the owner's to make.

**F2 — 🟠 Gemini's OpenAI-compatible tool-calling refuses this repo's strict plan schema.**
Measured live: `finish_reason: function_call_filter: MALFORMED_FUNCTION_CALL`, `completion_tokens: 0`,
`tool_calls: None` — **with and without `strict: true`**, and with both a short and the full
1.3k-token manifest prompt. A hand-built flat schema and a `$defs`/`$ref` schema both succeed on
the same key and model, so it is this schema, not the endpoint. I did **not** work around it:
stripping `strict` or reshaping the frozen `submit_plan` contract from the transport layer would
silently weaken the guarantee the design exists for, and both are outside the granted exception.
Consequence today is benign and by design — `demo … --llm` prints
`plan: heuristic(fallback: PlannerError: LLM returned no tool call)` and still ends `pass 8/8`.
Documented in `docs/USER-TEST.md` step 13 + "Known quirks". Phase 08 item: negotiate the
per-provider tool schema once, in the planner, with a test that pins both providers.

**F3 — 🟠 `src.cli.main run` still gates the LLM attempt on `OPENAI_API_KEY` alone.** With only
`GEMINI_API_KEY` set, `run` plans heuristically and never touches the router; `demo … --llm`
does reach it. `src/cli/main.py` is outside this phase's grant, so it is reported, not fixed.
One-line fix when wanted: `offline = args.offline or not (os.environ.get("OPENAI_API_KEY") or
os.environ.get("GEMINI_API_KEY"))`. Documented in step 13 caveat 2.

**F4 — 🟡 Google's bad-key answer is 400, not 401.** Found by the live run: a dead key returns
`400 INVALID_ARGUMENT — "Please pass a valid API key"`. A status-only classifier would have
treated that as a fatal request error and taken the whole run down on the first dead key, which
defeats the point of holding N keys. The router now also recognises a key fault by wording on a
400 (`KEY_FAULT_TEXT`), and the live transcript above is pinned by
`test_a_bad_key_reported_as_400_still_fails_over`.

**F5 — 🟡 the pre-publish scan caught a test canary I wrote.** `SECRET = "AIza…"` in the router
test tripped `assigned_secret` (`2 failed` in `test_security_hardening.py`). `src/security/scan.py`
is frozen and its `ALLOWLIST` is marker-based, so the fix belonged on my side: the fixture is now
named `FAKE_KEY` with a comment saying it is a shape, not a key. Findings back to 0. Worth
knowing: `AIza…` Gemini keys match **none** of the scan's patterns, so a real one committed by
accident would not be caught — the `GEMINI_API_KEY*` variable names would have to be scanned
separately.

**F6 — 🟡 expected-output drift.** `README.md`, `SUBMISSION.md`, `demo/script.md` and
`demo/video-script.md` all quote `114 passed` and a `replayed=1` cold demo; the suite is now
`127 passed, 1 skipped`. All four are read-only for this phase, so `docs/USER-TEST.md` carries the
current numbers. One-line refresh each when they are next editable.

**Mismatches between the BUILD's criteria and reality — none.** Every expected-output block
matched its live run on a cold `/tmp`; the only two places the runbook needed correcting were
my own drafts (a step-11 snippet that selected the wrong run directory, and a `--keep-url` flag
I documented but did not implement).

---

## Design notes, for the reviewer

- **Reused, not reinvented:** `RetryPolicy` (exponential backoff + deterministic jitter) and
  `classify()` (retryable-vs-fatal triage) already exist in `src/reliability/retry.py`; the router
  imports both. `contracts.events.redact` is the scrubber of last resort. `scripts/browser_check.py`
  reuses the demo's own sim spawner (`free_port`/`start_sim`/`wait_sim`) instead of forking it.
- **Rotation survives a run.** `router()` caches one `Router` per key set, otherwise a fresh
  router per `make_plan` call would restart at key #1 every time and N keys would be worth one.
- **The endpoint owns its model.** `create()` replaces the caller's `model=` per attempt; the
  `model` argument of `llm_plan` is kept only for the signature. This is why `demo --llm` with a
  `CENTRALIGN_MODEL=gpt-…` still calls Gemini correctly.
- **Drop-in shape.** `Router.chat.completions.create(**kw)` is the same surface the frozen
  planner already used, so `_step_args()` needed no edit at all.
- **ponytail:** the router keeps one cooldown for both key faults and transient overloads (60s,
  `COOLDOWN_S`) and one attempt per key per call. Per-fault cooldown windows and a same-key retry
  inside a call are the knobs to add if a 429 proves too blunt in production.

## Help needed

1. **Rotate the pasted Gemini key** (F1) — the owner's action, nothing for me to change.
2. **F2 decision:** is a per-provider tool schema (drop `strict` for Gemini, keep it for OpenAI,
   prove both in a test) in Phase 08 scope? Until then `--llm` on Gemini degrades to the
   heuristic plan and the rotation still works — which is the honest claim in the runbook.
3. **F3:** green-light the one-line `cmd_run` key check, or leave `run` as OpenAI-only by design.