# SUBMISSION — CentrAlign AI operator

**One-line:** an AI employee that turns *"find the latest invoice from Company X and post it to
the ERP"* into a verified, evidenced, approval-gated completion — demonstrated in 0.4 seconds,
offline, with no API key.

- **Repo:** `GITHUB_URL: <fill after push>` — e.g. `https://github.com/<your-handle>/centralign`
- **Video:** `VIDEO_URL: <fill after upload>` (unlisted link; 75–90s, beat sheet and record steps
  in [`demo/video-script.md`](demo/video-script.md))
- **One command:** `bash demo/run.sh` → `verdict: pass 8/8 · ERP count: 1`
- **Proof:** `python3 -m pytest tests/ -q` → 127 passed · `python3 -m src.security.scan` → 0 findings

## The narrow-genuine statement

> **Scope is one workflow — invoice intake for one company profile — executed for real, not
> simulated.** Three seeded invoices are genuinely parsed, the newest one for *that company* is
> genuinely selected (an invoice belonging to another company is present and ignored), the ERP
> genuinely gains exactly one row over HTTP, and the approval genuinely blocks until a human
> signs. Nothing on the demo path is a mock, stub or recorded fixture: there is no canned
> response, and the only network is `127.0.0.1`. What is *not* done — other domains, other
> systems, parallel execution, semantic recall — is listed in the README's Limits section rather
> than faked. A generalization gap we found while writing this file is named there too: the
> heuristic planner's find step globs `*.pdf`, so the seeded `.txt` invoice is never seen.

## Evaluation criteria → where to look, and what proves it

| criterion | how the system meets it | proof an evaluator can run |
|---|---|---|
| **Autonomy** — determines and executes next actions without being told every step | The planner builds a DAG from the request plus the declared tool manifests; no step names are hardcoded in the CLI. A human is involved exactly once, at the money threshold, because the company policy says so | `bash demo/run.sh` — `run 1` finds + gates, `run 2` resumes and posts, no step was named by the operator |
| **Execution** — actually performs work | `invoice_find_latest` parses files on disk; `erp_post_invoice` POSTs to a real HTTP server with a real sqlite DB | `ERP count: 1`; `cat runs/<id>/evidence.json` shows the tool args and the returned ERP row |
| **Reliability** — unexpected states, errors, retries, failure | Append-only ledger, retry-with-backoff on retryable failures, replan on a failed sweep, checkpoint/resume, idempotency index so a re-run re-executes nothing | `bash demo/run.sh --append` → `replayed=2`, `ERP count: 1` (unchanged); `tests/test_reliability_offline.py` — retries, backoff, resume, replan |
| **Verification** — did the outcome actually happen? | An independent verifier re-derives six gates plus one criterion per step **from the ledger rows**, not from the executor's return value; anything unresolved reads `blocked`, never `pass` | `verdict: pass 8/8` line; the 8 predicates are printed in `evidence.json`; `python3 -m src.cli.main run --task ""` → `blocked / No task given`, rc=1 |
| **Generalization** — what survives a different task? | The runtime, gate, verifier, ledger, memory and evidence layers are domain-agnostic; company knowledge lives in versioned `context/*.yaml` (tools, allowlist, ceilings, PII rules) and in tools that satisfy the frozen `ToolManifest` contract | A new domain is a new `context/` profile + tool manifests; the empty-task case shows the loop refusing to fake a plan |
| **Engineering Quality** — architecture, code, judgment | Frozen pydantic contracts, one chokepoint per trust boundary (`files_tool.safe_path`, `browser_tool.check_url`, `gate.decide`), stdlib-first, 5 pinned deps, contract-bound types instead of dicts, and a pre-publish security scan that fails CI | `python3 -m src.security.scan` → `findings: 0`; `python3 -m src.cli.main doctor` → one line per readiness check |
| **Product Thinking** — focused on the user's actual objective | The system is graded on the user's outcome (invoice in the ERP), not on steps completed. `replayed=N` exists so a cached pass is never presented as an executed one; the CLI always ends with the next action, never a dead end | `ERP count: 1 (unchanged: nothing was double-posted)`; every blocked run prints the exact command that unblocks it |
| **Technical Understanding** — why it is built this way | The design separates *planning* (model) from *execution and proof* (code); the verifier is deliberately given no access to the executor's conclusion; the ledger is append-only so a resumed run can never rewrite history | This file, the README's Decisions section, and the per-phase `REPORT.md`s under `prompts/` (each records raw command output, design choices and known ceilings) |

## What the LLM path has actually been exercised on

Evaluators should read the **Technical Understanding** row with this beside it, because "the model
plans" is not the same claim as "the model was proven":

- **Proven, and it is what you will see.** The deterministic heuristic planner runs the whole loop
  offline — `verdict: pass 8/8`, no key, no network. This is the demo, the video, and the 127 tests.
- **Proven live *and* in tests.** The multi-key router (`src/llm/router.py`): round-robin over every
  key in the environment, 429 / 5xx / bad-key → cool that key and fail over to the next inside one
  call, and no key material in any log or exception. Measured against the real Gemini endpoint with
  a deliberately dead key first (400 `INVALID_ARGUMENT` → cooldown → next key OK) plus a live 429;
  `tests/test_llm_router_keys.py` pins all of it offline.
- **Falls back by design.** Gemini's OpenAI-compatible endpoint refuses this repo's *strict* plan
  schema — measured live as `MALFORMED_FUNCTION_CALL`, `completion_tokens: 0`, with and without
  `strict: true`, while a hand-built flat schema succeeded on the same key and model. So
  `demo --llm` on Gemini ends `plan: heuristic(fallback: PlannerError: LLM returned no tool call)`
  and still ends `pass 8/8`. The planner treats any contract violation as a fallback rather than
  stripping `strict` to look better.
- **Unexercised.** The OpenAI-key path — no `OPENAI_API_KEY` was ever run against the live endpoint,
  so it carries no live evidence. Only the router code it shares is tested.

## What a reviewer should run, in order

```bash
bash demo/run.sh                      # the 30-second demo, offline, no key
bash demo/run.sh --append             # replay beat: nothing re-executes
python3 -m src.cli.main doctor        # readiness, exit 0
python3 -m src.cli.main run --task "find latest invoice from Company X and post it to the ERP" \
        --runs /tmp/x/runs --queue /tmp/x/gate.jsonl   # same loop, no demo script, waits for a human
python3 -m src.reliability.hitl --pending        # the approval queue a human sees
python3 -m pytest tests/ -q           # 127 tests
python3 -m src.security.scan          # 0 findings
```

The `run` line above stops at `blocked / 7/8` with `ERP count: 0` — that is the gate working,
not a broken command. It prints the exact `--approve` line to continue.

## Honest limits (not hiding these)

Single workflow and single company profile; pattern-based redaction rather than DLP; the
verifier checks eight ledger-derivable properties and cannot judge business correctness; BM25
recall with no embeddings; serial step execution; approval requests keyed on
`(tool, amount, domain)`; one replan shape; the demo's approval is unattended sign-off by
name. Full list with rationale: **README → Limits**.

## Deliverables checklist

- [ ] GitHub/source link — `GITHUB_URL: <fill after push>` (not yet real; see **USER-STEPS.md**)
- [x] README with setup + run instructions (`bash demo/run.sh`, `pytest`, `doctor`, `scan`)
- [x] Architecture explanation (README diagram + table; per-phase `prompts/*/REPORT.md`)
- [x] Working prototype, genuinely executed, not mocked
- [x] Evidence returned per run (`runs/<id>/evidence.json`, `events.jsonl`, `state.json`)
- [ ] Video — `VIDEO_URL: <fill after upload>` (script + recording steps in
      [`demo/video-script.md`](demo/video-script.md); not yet recorded)