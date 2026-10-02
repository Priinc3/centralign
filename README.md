# CentrAlign — an AI operator that turns a company request into completed, verified work

**The 30-second pitch.** You say *"find the latest invoice from Company X and post it to the
ERP"*. CentrAlign picks the tool, reads the source, notices the posting exceeds the
company's unattended limit, stops and asks a human to approve, posts it, and then hands you
a verdict — `pass 8/8` — plus an evidence bundle you can read. It runs in **0.4 seconds,
offline, with no API key**, and every claim in the bundle is a row in an append-only ledger
rather than the executor's opinion. A narrow slice of company work done genuinely, not a
broad surface where most things are mocked.

## Quickstart — under 60 seconds

### Watch it run (the UI)

```bash
python3 -m src.ui.app --port 0
```

Open the `http://127.0.0.1:<port>` it prints. Then **three clicks**: `Run the task` → the amber
banner `blocked / 7/8 predicates passed` and an approval card naming the amount → `Approve` →
green `pass 8/8   replayed=1` with one real row in the ERP → `Run again (run 2)` → `replayed=2`,
still one row. No install. Without a key the page runs the deterministic fallback plan offline and
says so on its badge; with a key it asks a real model. The only thing it talks to is a simulated ERP
on `127.0.0.1` that the command starts and stops. Scratch under `/tmp/centralign-ui` is wiped at
startup, so the first click is always cold.

The page has no offline mode: it asks a real model to write the plan on every run. With
`GEMINI_API_KEY`, `GROQ_API_KEY` or `OPENAI_API_KEY` in the environment the badge names the model
that answered — currently `llm · groq/qwen/qwen3.8-27b`, proven live at `pass 8/8` and `9/9`.
With no key the plan is the
deterministic one and the badge says so (`model fallback: …`), exactly as the CLI does. Model calls
take seconds on Groq and 30–60 s on Gemini; `GEMINI_MODEL` overrides the Gemini model (note: new
Google projects retired `gemini-2.5-flash` — use `gemini-3.8-flash`). The page binds
`127.0.0.1` only and refuses any other host — it approves money. While a run is in flight the page
polls twice a second; a finished page makes zero requests.

### Or run it from the terminal (same loop, no browser)

```bash
bash demo/run.sh
```

It creates a scratch ERP + ledger under `/tmp/centralign-demo`, runs the whole loop, and prints:

```
seed        3 files in data/seed/invoices, newest = CX-2024-0912 $4,820.00 due 2024-10-12
erp rows    0
task        find latest invoice from Company X and post it to the ERP

run 1  2ed307f6234b
  ✓ s1  invoice_find_latest    CX-2024-0912  $4,820.00 USD  due 2024-10-12
  ⏸ s2  erp_post_invoice       not posted — waiting for a human to approve it (queued below)

1 approval needed before this can continue:
  ✓ ce20c8f39d98  erp_post_invoice $4,820.00  approved by demo-operator   (erp_post_invoice requires approval)

run 2  continuing 2ed307f6234b  (new run id: the ledger is append-only)
  ↻ s1  invoice_find_latest    CX-2024-0912  $4,820.00 USD  due 2024-10-12
  ✓ s2  erp_post_invoice       ERP row #1 created

verdict: pass 8/8   replayed=1   plan: heuristic   run: b9b8727b134e
ERP count: 1
evidence: /tmp/centralign-demo/runs/b9b8727b134e/evidence.json
```

Copied from a real run (run ids and the ERP port are random per run, so yours will differ — the
steps, `replayed=` numbers and counts will not).

Then, four commands that tell you more than the first one did:

```bash
bash demo/run.sh --append      # same scratch, same task: replayed=2, ERP count still 1
python3 -m src.cli.main doctor # is this machine ready? exit 0 = yes, offline
python3 -m pytest tests/test_ui_offline.py -q   # drive the page over HTTP, no browser needed
cat /tmp/centralign-demo/runs/*/evidence.json | head -40   # plan, ledger rows, verdict
```

Full suite (163 tests, ~16s) and the pre-publish security scan:

```bash
python3 -m pip install -r requirements.txt   # optional: neither the demo nor the page needs any of it
python3 -m pytest tests/ -q
python3 -m src.security.scan                # 0 findings = safe to publish
```

## Architecture

```
                  ┌────────────── contracts (frozen pydantic) ──────────────┐
                  │  ToolManifest   Event envelope   Verdict               │
                  └───────┬───────────────────────────────────────┬────────┘
   Goal ──▶ Understand ──▶ Plan ──▶ Execute ──▶ Observe ──▶ Adapt ──▶ Verify ──▶ Complete
             intent +     DAG      idempotent   StepResult   replan   8 predicates  Verdict
             manifest     steps    call + gate  + evidence   on      vs ledger    + evidence
                        ▲                    ▲                failure            bundle
                        │                    │                                   ▲
              planner (LLM or         authorizer = policy gate                 │
              heuristic fallback)     + HITL queue                             │
                                                                               │
   ledger (sqlite, WAL, append-only) · evidence bundle · memory store · policy YAML
```

| stage | file | what it decides |
|---|---|---|
| Understand | `src/runtime/loop.py:125` | intent + which declared tools could serve it |
| Plan | `src/runtime/planner.py` | a DAG of steps — LLM tool-calling, or a deterministic fallback |
| Execute | `src/runtime/executor.py` | one attempt = ledger row + redacted event, before *and* after |
| Observe / Adapt | `src/runtime/loop.py:154`, `src/reliability/replan.py`, `retry.py` | next action from the last result; retry with backoff, else replan |
| Verify | `src/verifier/checks.py` | six gates + one criterion per step, graded against the ledger |
| Approve | `src/policy/gate.py`, `src/reliability/hitl.py` | allow / approve / deny, every decision logged |
| Remember | `src/memory/store.py` | company facts in SQLite FTS5, PII-redacted on write |
| Evidence | `src/ledger/evidence.py` | `evidence.json` + `events.jsonl` + `state.json` per run |

The verifier never reads the executor's conclusion — it re-derives pass/fail from the ledger
rows. That is the whole point of the design: the thing that grades the work did not do the work.

## Decisions and why

- **The LLM plans; deterministic code executes.** Planning is the one step that benefits from
  a model. Execution, gating, verification and evidence are code, because they have to be
  auditable and repeatable. No API key → the planner emits a heuristic plan and the run
  continues (`plan: heuristic` is printed on the verdict line, never hidden).
- **Deny by default.** A tool not in `context/tools.yaml` is denied, not allowed. A domain not
  in the allowlist is denied regardless of amount. An amount over the company ceiling is
  refused rather than queued — a queue implies someone might say yes.
- **The ledger is append-only, so resuming is a new run.** A run id is never rewritten; the
  resumed run points at the one it continues. Evidence is therefore always a coherent history.
- **Idempotency index over cached results.** `replayed=N` on the verdict line separates "this
  passed from the ledger" from "this executed now" — a reader never has to open the bundle to
  tell which claim they are looking at.
- **An approval is a person in the audit trail.** `$4,820 > $1,000` unattended limit, so the
  run stops, writes a request to `gate.jsonl`, and prints the exact command to approve. The
  approver's name is recorded. Unattended sign-off (`--approve demo-operator`) exists for the
  demo and CI and is labelled as such.
- **Evidence before summary.** Every run writes the bundle before the CLI prints anything.
  If a tool did not run, the bundle says so — no silent mock autonomy.
- **stdlib-first.** `http.server` + `sqlite3` for the sim ERP, no Flask; 5 runtime deps
  (`openai`, `pydantic`, `pyyaml`, `pytest`, optional `playwright`), pinned in `requirements.txt`.

## Models and APIs

| use | what is used | when it is skipped |
|---|---|---|
| planning | OpenAI-compatible chat completions, strict tool-calling, behind a multi-key router (`$GEMINI_API_KEY[_2..]`, then `$GROQ_API_KEY[_2..]`, then `$OPENAI_API_KEY[_2..]`); a Gemini endpoint gets a title-free schema profile at `temperature: 0`, a Groq endpoint gets inlined `$defs`, no bare `required`, no `strict`, and `max_tokens: 800`, an OpenAI endpoint gets the tool byte-identical | no key in the environment, or an answer that is not a valid plan → the deterministic heuristic planner runs and says so — `plan: heuristic` / `plan: heuristic(fallback: …)`. Proven live on Gemini (`plan: llm:gemini/gemma-4-31b-it`) and on Groq (`plan: llm:groq/qwen/qwen3.8-27b`). See below for exactly what has and has not been exercised live |
| invoice source | seeded files in `data/seed/invoices` (3 PDFs/CSVs) | — |
| ERP | `sim_app/server.py`, stdlib `http.server` + sqlite on `127.0.0.1`, started and stopped by the demo | — |
| browser | Playwright chromium, URL allowlist, auto-wait | optional dep; nothing in the demo or the suite needs it |
| memory / ledger | SQLite in WAL mode | — |

### What the LLM path has actually been exercised on

Stated exactly, because "we use an LLM" is not the same claim as "we proved an LLM":

- **Proven, and it is what you will see.** The deterministic heuristic planner runs the whole
  loop offline — `verdict: pass 8/8`, no key, no network.
- **Proven live, with the model in the loop.** With a key exported, the CLI demo's `--llm`
  gets a real plan back from a real model and the verdict line names it
  (`plan: llm:gemini/gemma-4-31b-it`, `finish_reason: tool_calls`, still `pass 8/8`), and the page
  — which has no flag, it always asks — plans with `llm:groq/qwen/qwen3.8-27b` at `pass 8/8` and
  `9/9` on the invoice scenarios. The model picks the tools, their order, the DAG and
  the success criteria; the two values it could not know (`amount`, `due_date`) are not invented —
  the step emits `{{s1.latest.amount}}` refs and the executor resolves them out of the read step's
  own result, so the ERP row matches the invoice byte for byte. Full transcript, including the row
  read out of the sim ERP: `prompts/phase-12-gemini-planning/REPORT.md`.
- **What it took to get there, measured.** Gemini's OpenAI-compatible endpoint rejected this repo's
  strict plan schema — `finish_reason: function_call_filter: MALFORMED_FUNCTION_CALL`,
  `completion_tokens: 0`, with and without `strict: true`, with `$defs` inlined, with `args`
  dropped. Eleven schema variants later the one common factor was `title`, the key pydantic puts on
  every model. The router now sends a Gemini endpoint a profile with **only** `title` removed
  (`strict: true` kept, `temperature: 0` so the plan is reproducible); an OpenAI endpoint still gets
  the tool byte-identical and no imposed temperature. We did not strip `strict` to make it look
  better; that guarantee is the point of the design.
- **Falls back by design, not by accident.** No key, exhausted quota, a 4xx, or a plan that violates
  the contract → `plan: heuristic(fallback: <reason>)`, the heuristic plan intact, and the run still
  ends `pass 8/8` with the reason printed on the verdict line. Verified with no key at all.
- **Ceilings, measured.** `gemma-4-31b-it` is slow — ~1.3k-token manifest prompt, ~30–60 s per call,
  and the two-run `demo --llm` cycle measured **159 s** because resuming re-plans.
  Free-tier physics, measured Oct 2026: Gemini allows 20 requests/day/key (`429` after that, all
  keys spent at the time of writing — Gemini is first in line for after the reset); new Google
  projects retired `gemini-2.5-flash` (`404`, use `gemini-3.8-flash`, which 503s under load);
  Groq's on-demand tier caps *output* at 1000 tokens/min and 429s an uncapped estimate, so Groq
  calls carry `max_tokens: 800`. No Llama chat model exists on the Groq account (all 404) and
  gpt-oss intermittently refuses its own registered tool — `qwen/qwen3.8-27b` is the default
  because it tool-calls cleanly (`GROQ_MODEL` overrides).
- **Proven live *and* in tests.** The multi-key router (`src/llm/router.py`): every key in the
  environment used round-robin, a 429 / 5xx / bad-key answer cools that key and fails over to the
  next within one call, and no key material reaches a log or an exception. Measured against the
  real Gemini endpoint with a deliberately dead key first (400 `INVALID_ARGUMENT` → cooldown
  → next key OK) and a live 429; `tests/test_llm_router_keys.py` pins all of it offline.
- **Unexercised.** The OpenAI-key path. No `OPENAI_API_KEY` was ever run against the live
  endpoint, so it carries no live evidence — only the shared router code is tested. Gemini's
  live proof stands (phase 12) but every Gemini key to hand is quota-spent; Groq/qwen is the
  currently-green path (phase 13 postscripts).

## Security posture

- **Deny by default** at the gate (`src/policy/gate.py`), the browser allowlist
  (`src/tools/browser_tool.py`, exact host or a real subdomain — `example.com.evil.com` is
  refused), and the `data/` filesystem sandbox (`src/tools/files_tool.py`, `..`, absolute
  paths, `~` and NUL all refused).
- **Secrets never reach disk.** Every event, checkpoint, ledger row, memory fact and evidence
  file passes through the redactor (`src/contracts/events.py:redact`) *before* the write —
  secret-looking keys, `Bearer <tok>` and `sk-…` values are masked recursively.
- **`python3 -m src.security.scan`** proves it at publish time: credential patterns across
  `src/ context/ sim_app/ demo/ tests/ runs/`, a marker-checked allowlist for the two
  deliberate test canaries, no `.env` in the tree with `.gitignore` covering one, and live
  self-tests that the four guards above still deny (plus a positive control that the redactor
  still masks a live secret). ~0.3s.
- **No credentials in the repo.** `GEMINI_API_KEY`, `GROQ_API_KEY` and `OPENAI_API_KEY`
  (plus numbered rotation slots) are read from the environment only.

## Assumptions

1. Invoice intake is the vertical: read a source document, enter a record in an internal
   system, prove it happened.
2. Company context (tools, allowlist, ceilings, PII rules) is versioned YAML a human edits —
   `context/*.yaml`, validated at load.
3. One SQLite writer per process; WAL mode; the ledger is the source of truth for "what
   happened", the evidence bundle is derived from it.
4. `127.0.0.1` is trusted; anything else must be allowlisted.
5. Humans are reachable synchronously for approvals (a queue plus a CLI, not Slack).

## Limits — stated, not hidden

- **One workflow, one company profile.** The planner heuristic recognizes invoice intake;
  another domain needs another `context/` profile and tool set (the machinery is generic, the
  knowledge is narrow). Known gap: the heuristic find step globs `*.pdf`, so a seeded `.txt`
  invoice is never seen — `invoice_find_latest` itself parses it fine when asked directly.
- **The demo's approval is `--approve demo-operator`**, an unattended sign-off. Interactive use
  should answer the prompt; the name recorded is real either way.
- **Redaction is pattern-based.** It masks credential shapes and the four PII patterns in
  `policies.yaml`; a name typed in prose is not detected. This is a scanner, not a DLP product.
- **The verifier checks eight things it can check from the ledger** (goal non-empty, plan
  non-empty, every step resolved, no silent skips, evidence per success, audit trail
  complete, per-step criteria). It cannot judge whether the *business* outcome was right.
- **Memory recall is keyword/FTS5 + BM25**, single-writer, no embeddings. `CREATE VIRTUAL
  TABLE` needs an FTS5-enabled SQLite.
- **No parallelism.** Steps run in topological order, one at a time; the browser path is
  synchronous Playwright.
- **Approval requests key on `(tool, amount, domain)`** — two genuinely different postings of
  the same amount share one request.
- **Replan has one shape**: re-plan once per failed sweep. A deeper search is not implemented.
- **The sim ERP is a subprocess.** If the interpreter running the demo differs from the one
  that launched the sim, the port/db can disagree; the demo's `/health` db check catches it.

## What is next

1. **Real connectors instead of the sim** — the ERP tool already speaks HTTP; point it at a
   real endpoint behind the same gate.
2. **Embeddings + hybrid recall** in `src/memory` for facts that keyword search misses.
3. **Broader domain via `context/` profiles** rather than new code: the planner, gate and
   verifier are already domain-agnostic.
4. **Parallel step execution** for independent DAG branches, with the ledger keeping the
   single-writer guarantee via one queue.
5. **Signed, tamper-evident evidence** (hash chain over ledger rows) so a bundle can be shown
   to a third party without trusting the machine that wrote it.

## Repo layout

```
src/contracts/   frozen pydantic contracts (ToolManifest, Event, Verdict)
src/runtime/     loop, planner, executor
src/tools/       files (sandboxed), invoice parser, ERP client, browser (allowlisted)
src/policy/      YAML context loader, risk-tiered gate
src/memory/      company facts: SQLite WAL + FTS5, PII-redacted on write
src/reliability/ retry/backoff, replan, checkpoint/resume, HITL approvals
src/verifier/    independent predicates over the ledger
src/security/    pre-publish scan
src/ui/          the demo page: stdlib http.server + one HTML file, no build step
src/cli/         demo / run / doctor
context/         company.yaml, policies.yaml, tools.yaml  (versioned, human-edited)
data/seed/       3 seeded invoices
sim_app/         stdlib sim ERP
demo/            run.sh, script.md, video-script.md
tests/           163 tests, offline, no API key
prompts/         the build phases and their reports
```

## Proven, not claimed

```
$ bash demo/run.sh /tmp/d6          → verdict: pass 8/8   replayed=1   ERP count: 1   0.427s
$ bash demo/run.sh /tmp/d6 --append → verdict: pass 8/8   replayed=2   ERP count: 1
$ python3 -m src.ui.app --port 0    → Run → Approve → Run again: pass 8/8 replayed=1 → replayed=2, ERP rows 1
$ python3 -m pytest tests/ -q       → 163 passed, 1 skipped
$ python3 -m src.security.scan      → findings: 0  → safe to publish
$ python3 -m src.cli.main doctor    → ready: the offline demo runs
```

Counts and verdicts are exact; the one timing is a single measured run on a laptop and moves a few
tenths of a second each time. Reproduced in `prompts/phase-08-submission/REPORT.md` (terminal) and
`prompts/phase-11-video-ui/REPORT.md` (page).

Video: `demo/video-script.md` (75–90s, every beat matches this output, with the shoot in its
`RECORDING.md` section). Submission map: `SUBMISSION.md`.