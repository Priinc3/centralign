# SUBMISSION — CentrAlign AI operator

Role: AI Engineering Intern (prototype also demonstrates Founding-scope architecture — see video close)

**One-line:** an AI employee that turns *"find the latest invoice from Company X and post it to
the ERP"* into a verified, evidenced, approval-gated completion — planned by a real model
(`llm:groq/qwen/qwen3.8-27b`), `pass 8/8` and `9/9` on the invoice scenarios, with a deterministic
offline fallback that says so on the badge when no key works.

- **Repo:** https://github.com/Priinc3/centralign
- **Video:** https://drive.google.com/file/d/1cgjTLso1PJflQ_-UQxXVWYsbXhDQq8hh/view?usp=sharing (beat sheet and record steps in [`demo/video-script.md`](demo/video-script.md))
- **One command:** `bash demo/run.sh` → `verdict: pass 8/8 · ERP count: 1`
- **The page:** `python3 -m src.ui.app --port 0` — online-only, Run → Approve → Run again
- **Proof:** `python3 -m pytest tests/ -q` → 163 passed · `python3 -m src.security.scan` → 0 findings

## The narrow-genuine statement

> **Scope is invoice work for one company profile across three scenarios — executed for real,
> not simulated.** Seeded invoices are genuinely parsed, the newest one for *that company* is
> genuinely selected (an invoice belonging to another company is present and ignored), the ERP
> genuinely gains exactly one row over HTTP, and the approval genuinely blocks until a human
> signs. Nothing on the demo path is a mock, stub or recorded fixture: there is no canned
> response, and the only network is `127.0.0.1` plus the model endpoint when a key is exported.
> What is *not* done — other domains, other systems, parallel execution, semantic recall — is
> listed in the README's Limits section rather than faked.

## Evaluation criteria → where to look, and what proves it

| criterion | how the system meets it | proof an evaluator can run |
|---|---|---|
| **Autonomy** — determines and executes next actions without being told every step | The model builds a DAG from the request plus the declared tool manifests (tools, order, dependencies, success criteria); no step names are hardcoded. A human is involved exactly once, at the money threshold, because the company policy says so | Page scenario 1 and 2, or `bash demo/run.sh` — `run 1` finds + gates, `run 2` resumes and posts, no step was named by the operator |
| **Execution** — actually performs work | `invoice_find_latest` / `files_list` / `invoice_parse` read files on disk; `erp_post_invoice` POSTs to a real HTTP server with a real sqlite DB | `ERP count: 1`; `cat runs/<id>/evidence.json` shows the tool args and the returned ERP row |
| **Reliability** — unexpected states, errors, retries, failure | Append-only ledger, multi-key rotation with cooldown/failover, retry-with-backoff on retryable failures, replan on a failed sweep, checkpoint/resume, idempotency index so a re-run re-executes nothing; any LLM failure degrades to the heuristic with the reason on the badge | `bash demo/run.sh --append` → `replayed=2`, `ERP count: 1` (unchanged); `tests/test_reliability_offline.py`, `tests/test_llm_router_keys.py` |
| **Verification** — did the outcome actually happen? | An independent verifier re-derives six gates plus one criterion per step **from the ledger rows**, not from the executor's return value; anything unresolved reads `blocked`, never `pass` | `verdict: pass 8/8` / `pass 9/9`; predicates printed in `evidence.json`; `python3 -m src.cli.main run --task ""` → `blocked / No task given`, rc=1 |
| **Generalization** — what survives a different task? | The runtime, gate, verifier, ledger, memory and evidence layers are domain-agnostic; company knowledge lives in versioned `context/*.yaml` and in tools satisfying the frozen `ToolManifest` contract. Scenario 2 and 3 run through the same loop with different tasks | Same commands, different scenario card; the empty-task case shows the loop refusing to fake a plan |
| **Engineering Quality** — architecture, code, judgment | Frozen pydantic contracts, one chokepoint per trust boundary, stdlib-first, pinned deps, contract-bound types instead of dicts, per-provider LLM wire profiles with live-measured comments, and a pre-publish security scan | `python3 -m src.security.scan` → `findings: 0`; `python3 -m src.cli.main doctor`; per-phase `prompts/*/REPORT.md` record raw output and ceilings |
| **Product Thinking** — focused on the user's actual objective | Graded on the user's outcome (invoice in the ERP), not steps completed. `replayed=N` separates cached passes from executed ones; the badge never shows a model that did not plan the run | `ERP count: 1 (unchanged: nothing was double-posted)`; fallback badge reads `model fallback: <reason>` |
| **Technical Understanding** — why it is built this way | Planning (model) is separated from execution and proof (code); the verifier never reads the executor's conclusion; the ledger is append-only so a resumed run cannot rewrite history | This file, the README's Decisions section, and the per-phase `REPORT.md`s under `prompts/` |

## What the LLM path has actually been exercised on

"the model plans" is not the same claim as "the model was proven":

- **Proven live, page, Groq.** `plan_source: llm:groq/qwen/qwen3.8-27b`, model-written intents,
  scenario 1 `pass 8/8`, scenario 2 `pass 9/9`. Transcript + key scoreboard:
  `prompts/phase-13-ui-story/REPORT.md` (postscripts).
- **Proven live, CLI, Gemini.** `plan: llm:gemini/gemma-4-31b-it`, `finish_reason: tool_calls`,
  `pass 8/8`. Transcript: `prompts/phase-12-gemini-planning/REPORT.md`.
- **What it took, measured.** Gemini's compat endpoint rejects `title` keys (kept everything else);
  Groq needs inlined `$defs`, no bare `required`, no `strict`, and `max_tokens: 800` (its on-demand
  tier caps output at 1000/min); no Llama chat model exists on the account and gpt-oss flakes on
  tool registration, so qwen is the default (`GROQ_MODEL` overrides). Router: round-robin,
  429/5xx/bad-key → cooldown + failover inside one call, one in-place retry on a flaked tool call,
  no key material in any log. Current key state: every Gemini key to hand is quota-spent (20/day),
  so Gemini is first in line for after the reset and Groq serves today.
- **Falls back by design.** No key, spent quota, 4xx, or a contract-violating plan →
  `heuristic(fallback: <reason>)`, run still verdicts honestly. The page has no offline mode —
  it always asks the model; the badge tells you what came back.
- **Unexercised.** The OpenAI-key path — no live key, only shared router code tested.

## What a reviewer should run, in order

```bash
python3 -m src.ui.app --port 0       # the demo in a browser — open the URL it prints,
                                      # pick a scenario, Run → Approve → done; ctrl-c stops it
bash demo/run.sh                      # the same loop from the terminal, offline, no key
bash demo/run.sh --append             # replay beat: nothing re-executes
python3 -m src.cli.main doctor        # readiness, exit 0
python3 -m pytest tests/ -q           # 163 tests
python3 -m src.security.scan          # 0 findings
```

With a key exported (`GEMINI_API_KEY`, `GROQ_API_KEY` or `OPENAI_API_KEY`), the page and
`bash demo/run.sh /tmp/x --llm` plan with the model and the badge/verdict line names it.

## Architecture (short)

Strict tool-calling planner (submit_plan, then per-step args) → executor (manifest dispatch,
ref resolution, approval gate) → verifier (ledger-derived predicates) → evidence bundle.
Multi-key LLM router underneath; deterministic heuristic fallback beside it. Full diagram +
stage table: **README → Architecture**.

## Important design decisions

1. **The model plans; code executes and proves.** The verifier never reads the executor's
   conclusion — it re-derives pass/fail from ledger rows.
2. **Deny by default** at the gate, the browser allowlist, and the filesystem sandbox.
3. **Append-only ledger**, so resume is a new run and evidence is always coherent history.
4. **Idempotency index**, so `replayed=N` separates cached passes from executed ones.
5. **Approvals are people in the audit trail** (`$4,820 > $1,000` unattended limit).
6. **Per-provider wire profiles** in the router (title-strip, def-inline, token cap) — each with
   the live measurement that forced it, in comments.
7. **Refs only where the shape holds**: a write step takes `{{dep.latest.*}}`; a read step
   after a list names its own file (scenario-2 postscript).

## Known limitations

Single workflow family, one company profile; pattern-based (not DLP) redaction; the verifier
judges ledger-derivable properties, not business correctness; keyword memory, no embeddings;
serial steps; one replan shape; sim ERP; free-tier quotas on every model path. Full list:
**README → Limits**.

## What I would build next (2 weeks)

Real ERP connector first (the tool already speaks HTTP); mid-run replan-on-failure instead of
degrade-to-fallback; Groq structured outputs + a local-model option to escape free-tier physics;
persistent company memory across runs. Full reasoning: README → What is next.

## Assumptions

Invoice intake is the vertical; company context is human-edited versioned YAML; one SQLite
writer, WAL, ledger = source of truth; `127.0.0.1` trusted, rest allowlisted; humans reachable
synchronously for approvals. Full list: **README → Assumptions**.

## Models, APIs, frameworks, components

Planner: `qwen/qwen3.8-27b` via Groq, Gemini first in line (`gemma-4-31b-it`, `gemini-3.8-flash`)
— all through the OpenAI Python SDK against OpenAI-compatible endpoints. Contracts: pydantic.
UI: stdlib `http.server` + one HTML file, no build step. Suite: pytest (163, offline, no key).
AI coding tools used: OpenCode, powered by Muse Spark — the per-phase `prompts/*/REPORT.md`
files record what was built, measured, and deliberately skipped. No other pre-built agent
frameworks; executor, verifier, router, ERP sim are custom code in this repo.

## Deliverables checklist

- [x] GitHub/source link — https://github.com/Priinc3/centralign
- [x] README with setup + run instructions
- [x] Architecture explanation (README + per-phase `prompts/*/REPORT.md`)
- [x] Technical/design decisions (README + this file)
- [x] Working prototype, genuinely executed, not mocked
- [x] Evidence returned per run (`runs/<id>/evidence.json`, `events.jsonl`, `state.json`)
- [x] Known limitations, next steps, assumptions, models/APIs (README + this file)
- [x] Video — https://drive.google.com/file/d/1cgjTLso1PJflQ_-UQxXVWYsbXhDQq8hh/view?usp=sharing (script + recording steps in
      [`demo/video-script.md`](demo/video-script.md))
