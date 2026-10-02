# REPORT — Phase 08 submission close-out

Four deliverables, four exception files touched, zero engine files. Every number in the packet was
re-derived from a run made today, not from a previous phase's report.

**Bottom line:** the packet is now internally consistent and every claim traces to a fresh run.
Two things block submission and both are yours: there is **no git repo** and **no video**. Both are
copy-paste blocks in `USER-STEPS.md`.

---

## The number that anchors every claim (BUILD deliverable 1)

```
$ python3 -m pytest tests/ -q
........................................................................ [ 56%]
......................................................s.                 [100%]
127 passed, 1 skipped in 7.36s
```

```
$ python3 -m src.security.scan
scanning 6 trees for credentials  … none
allowlisted canaries  2  (tests/, marker-checked: the line must still say why)
guards  deny unknown tool · deny evil host + suffix trick · deny /etc traversal · redactor masks a live secret

findings: 0  → safe to publish
```

```
$ python3 -m src.cli.main doctor
…
ready: the offline demo runs (python3 -m src.cli.main demo)
rc=0
```

**`127 passed, 1 skipped` is the count now in the packet.** Phase 07 recorded the drift as finding
F6 and could not touch the files; those four files are editable now and all six sites are fixed.

---

## Files changed, with line refs (post-edit line numbers)

### `README.md`
| line | change |
|---|---|
| 20–39 | Quickstart sample output regenerated from a real **default** `bash demo/run.sh` (was 3 stale run ids from an old run: `556805bef2a0` → `2ed307f6234b`, `c655e98cf0bf` → `ce20c8f39d98`, `97e8abd99663` → `b9b8727b134e`) |
| 41–42 | added: "Copied from a real run (run ids and the ERP port are random per run, so yours will differ…)" — stops the next reader filing this as drift |
| 52 | `114 tests` → **`127 tests`** (BUILD target 1) |
| 118 | Models table `planning` row: `$OPENAI_API_KEY` alone → `$GEMINI_API_KEY[_2..]` then `$OPENAI_API_KEY[_2..]`, and the row now says **multi-key router** |
| 124–143 | **new** `### What the LLM path has actually been exercised on` — the four honest claims (BUILD deliverable 2) |
| 223 | `tests/  114 tests` → **`127 tests`** (BUILD target 2) |
| 232 | `114 passed, 1 skipped in 7.11s` → **`127 passed, 1 skipped in 7.36s`** (BUILD target 3) |
| 230 | demo wall-clock `0.385s` → **`0.427s`**, re-measured today |
| 237–239 | added: timings are one measured run and move a few tenths; video pointer updated to name the `RECORDING.md` section and the 75–90s window |

### `SUBMISSION.md`
| line | change |
|---|---|
| 7–10 | `GITHUB_URL: <fill after push>` / `VIDEO_URL: <fill after upload>` as literal, pasteable lines (BUILD deliverable 3), with the expected handle spelled out |
| 11 | `114 passed` → **`127 passed`** (BUILD target 4) |
| 38–57 | **new** `## What the LLM path has actually been exercised on` — same four claims, written for the criterion-mapping reader |
| 68 | `# 114 tests` → **`# 127 tests`** (BUILD target 5) |
| 83–91 | deliverables checklist: **GitHub link and Video un-ticked** `- [ ]`, each saying why and where the real value comes from. They were `- [x]` on placeholder text — a false claim in the one file the evaluator reads first. |

### `demo/video-script.md`
| line | change |
|---|---|
| 36, 49, 59, 63, 81 | five run ids re-verified against the fresh run (§ Verified transcript) |
| 77–82 | replay beat **gained** the two `↻` step lines — the fresh append run prints both steps as `↻`, and those lines are the actual evidence for "nothing executed". The old script quoted only the verdict line while the narration claimed nothing re-executed. |
| 102, 104 | `114 passed` → **`127 passed`**, and the spoken line "One hundred and fourteen tests" → **"One hundred and twenty-seven tests"** (BUILD target 6) |
| 128–186 | **new** `## Verified transcript` — the verbatim fresh cold run + append + scan + suite, i.e. the appendix the BUILD asked to append |
| 188–221 | **new** `## RECORDING.md` — the shoot (see below) |

### `prompts/phase-08-submission/USER-STEPS.md` — new (BUILD deliverable 5)
Four copy-paste sections: git push (+ manual-remote fallback), video upload, the form-field table,
and the post-push re-check triple. Deliberately a prompt-file, not under `docs/`.

### `demo/script.md` — not on the BUILD's list, edited anyway
The 30-second script quoted the **same drift class** from the same stale run: approval id
`779cf5886178` with the wrong spacing and the wrong suffix text, plus three stale run ids. It is
inside the granted exception, and the phase goal is "every claim in the packet matches a fresh
run", so leaving it would have failed that goal on a file I was allowed to fix. Four ids and one
formatting fix, plus a note that ids are random per run. Flagging it because it is outside the
enumerated deliverables.

---

## The honest LLM claim (BUILD deliverable 2)

Same four statements in README and SUBMISSION, worded to the BUILD's spec and no further:

1. **offline heuristic proven (8/8)** — this is what the video, the demo and all 127 tests exercise.
2. **multi-key router + 429 failover proven live AND in tests** — live evidence is phase 07's
   transcript (dead key first → `400 INVALID_ARGUMENT` → cooldown → next key OK, plus a live 429);
   `tests/test_llm_router_keys.py` pins it offline. I re-verified the test file exists and covers
   both (`test_429_cools_the_key_and_fails_over_to_the_next`, `test_5xx_also_fails_over_and_a_key_
   stays_out_while_it_cools`, `test_a_bad_key_reported_as_400_still_fails_over`).
3. **full live plan-shape on Gemini falls back by design (F2)** — stated as the *measured reason*
   (`MALFORMED_FUNCTION_CALL`, `completion_tokens: 0`, with and without `strict: true`) and as the
   resulting string a reviewer will actually see (`plan: heuristic(fallback: PlannerError: LLM
   returned no tool call)`). I did **not** restate F2 as a solved problem: no per-provider schema
   work was done this phase, so the claim is "falls back by design", not "handled".
4. **OpenAI-key path unexercised** — said plainly, in both files, so nobody reads the router's
   tested failover as evidence for a provider that was never called.

Criterion check on the "no `strict tool-calling` promise without the fallback sentence in the same
paragraph": `strict tool-calling` occurs exactly once in the publishable docs — README:118 — and
its own table row ends "always falls back to the deterministic heuristic planner — `plan:
heuristic`. See below for exactly what has and has not been exercised live", with the detail section
immediately beneath the table.

---

## Fresh demo triple, and the script quotes checked against it

```
$ rm -rf /tmp/vid && bash demo/run.sh /tmp/vid
run 1  1539a7fa5c65
  ✓ s1  invoice_find_latest    CX-2024-0912  $4,820.00 USD  due 2024-10-12
  ⏸ s2  erp_post_invoice       not posted — waiting for a human to approve it (queued below)

1 approval needed before this can continue:
  ✓ 004e34e78f2b  erp_post_invoice $4,820.00  approved by demo-operator   (erp_post_invoice requires approval)

run 2  continuing 1539a7fa5c65  (new run id: the ledger is append-only)
  ↻ s1  invoice_find_latest    CX-2024-0912  $4,820.00 USD  due 2024-10-12
  ✓ s2  erp_post_invoice       ERP row #1 created

verdict: pass 8/8   replayed=1   plan: heuristic   run: c46011299453
ERP count: 1

$ bash demo/run.sh /tmp/vid --append
erp rows    1
run 1  32d361dade01
  ↻ s1  invoice_find_latest    CX-2024-0912  $4,820.00 USD  due 2024-10-12
  ↻ s2  erp_post_invoice       ERP row #1 created

verdict: pass 8/8   replayed=2   plan: heuristic   run: 32d361dade01
ERP count: 1  (unchanged: nothing was double-posted)
```

Rather than eyeballing the quotes, I extracted every terminal-output line from the fenced blocks of
`README.md`, `SUBMISSION.md`, `demo/script.md` and `demo/video-script.md` and tested each against
the concatenated raw output of three fresh runs (default scratch, `/tmp/vid` cold, `/tmp/vid
--append`) + scan, normalizing only the per-run randomness (12-hex run ids, ephemeral port,
scratch dir name):

```
✓ every quoted terminal-output line matches a fresh run (ids/ports/scratch normalized)
```

Two lines survive the filter as intentional non-matches, both verified by eye: `README.md:47` is a
shell command with a trailing comment, and `README.md:221` is a repo-layout line.

**Timing**, measured today rather than copied: cold `0.427s` wall (`--append`: `0.323s`), suite
`7.36s`. A later suite run came in at `7.25s`, so both files now say these are one measured run and
that the count is the part that must not move.

---

## Criteria, one at a time

| criterion | result |
|---|---|
| `grep -rn "114 passed" README.md SUBMISSION.md demo/` → empty | **PASS** — empty |
| `grep -rn "127 passed" README.md SUBMISSION.md demo/video-script.md` → 6 hits | **PASS** — 6 hits |
| no `strict tool-calling` promise without the fallback sentence in the same paragraph | **PASS** — 1 occurrence, fallback in the same table row |
| fresh demo triple matches the script quotes | **PASS** — programmatic check above |
| USER-STEPS commands dry-checked, flagging any that need the user's GitHub name | **PASS, with two flags** → below |

### Flag A — the 6-hit criterion is satisfied, but not the way the BUILD predicted

Of the six sites the BUILD enumerated, **four** are `passed`-shaped and two are count-of-tests lines
(`README.md` "Full suite (127 tests)", `SUBMISSION.md` "python3 -m pytest tests/ -q # 127 tests",
`demo/script.md`'s repo-layout line). Writing "127 passed" into those would be ungrammatical, so
they read "127 tests" and the literal grep reaches 6 only because the new Verified transcript and
RECORDING table added three more `127 passed` occurrences. **All six enumerated sites do carry the
correct refreshed number**; the grep's count comes from different lines than the BUILD predicted.
Not padding prose to move a grep.

### Flag B — the GitHub name

`gh auth status` on this machine: **logged in as `Priinc3`**, git protocol https, and git identity
`Prince <gondaliyaprince668@gmail.com>`. Every URL in `USER-STEPS.md` is written for
`github.com/Priinc3/centralign-operator` and every one is marked as "confirm this is the account you
want the submission under". `gh` is at `/opt/homebrew/bin/gh`; the manual-remote fallback is there
for when it isn't. **This is the one thing only you can confirm.**

### Other dry-checks run before writing USER-STEPS.md
- No `.env` anywhere in the tree.
- No key-shaped string (`sk-…`, `AIza…`, `gh[pousr]_…`) in `README.md`, `SUBMISSION.md`,
  `prompts/`, `docs/`, `demo/`, `context/` — the only `*.jsonl` outside ignored `runs/` is
  `data/gate.jsonl`, runtime state, ignored by two patterns.
- `.gitignore` already covers `runs/`, `*.db`, `*.jsonl`, `.env*`, `__pycache__/`, `.pytest_cache/`,
  `.DS_Store`. ~96 files would be staged; nothing that shouldn't be.
- Every command in USER-STEPS is one I ran in this session or a standard `gh`/`git` invocation with
  its flags spelled out. The `git clone --depth 1` re-check in step 4 cannot be run *now* — the
  repo does not exist remotely yet — which is why it is listed as the step you run after the push.

---

## RECORDING.md — what went into the video script

Appended inside `demo/video-script.md` as the BUILD asked (not as a separate file, so there is one
place to read before a take): 110×32 terminal with the reason wrapping looks like a bug, `clear`,
pre-flight warm run, and a 6-row keystroke table for the one-take order — cold (`rm -rf /tmp/vid`) →
`run.sh` → `--append` → `cat … evidence.json | head -30` → `security.scan` → `pytest`. 75–90s with
where to land each beat, cuts allowed only between blocks 3/4/5/6, **evidence first** to cut and
never approval or replay ("those two are the difference between an agent demo and an agent you can
trust"), upload **unlisted**, then paste `VIDEO_URL` into `SUBMISSION.md` and tick both boxes.

It also carries the caveat worth saying out loud on camera: `plan: heuristic` means this run needed
no key. Say it — do not let a viewer assume a model drove it. That is the same claim as README and
SUBMISSION, in the third place a reader might look.

---

## Remaining USER actions (nothing here is blocked on code)

1. `git init -b main; git add -A; git commit; gh repo create centralign-operator --public --source=. --push`
   → `git remote -v` to confirm → paste `GITHUB_URL` into `SUBMISSION.md` line 7 → tick its box at line 85.
2. Record per `demo/video-script.md` §RECORDING.md → upload unlisted → paste `VIDEO_URL` into
   `SUBMISSION.md` line 8 → tick its box at line 90.
3. Fill the form using the field table in `USER-STEPS.md` §3.
4. Re-check from a clean clone (`USER-STEPS.md` §4): `pytest` + `scan` + `demo` must read
   `127 passed, 1 skipped` / `findings: 0` / `pass 8/8 · ERP count: 1`.

## Out of scope, parked deliberately

- **F2 per-provider tool schema** (Gemini rejecting the strict plan schema) — BUILD says Phase 09,
  post-submit optional. Documented in both submission files as a live fallback, not as a fix.
- **F3** (`src.cli.main run` gates the LLM attempt on `OPENAI_API_KEY` alone, so `--llm` needs
  `demo --llm` to reach the router) — `src/` was read-only this phase; not fixed, not claimed fixed.
  Noted here so nobody discovers it as a surprise.
- **F1**, the Gemini key pasted in phase 07's chat, still needs rotating in Google AI Studio. It is
  the owner's disclosure to make; the tree is clean (`findings: 0`).

**Untouched, as required:** everything under `src/`, `tests/`, `scripts/`, `docs/`, `context/`,
`sim_app/`, `data/`, and every other `prompts/` REPORT/VERIFY and `docs/USER-TEST.md`. The only
`scripts/`-adjacent read was `prompts/phase-07-user-acceptance/REPORT.md` for the live-LLM evidence
I cite, and `src/llm/router.py` + `src/runtime/planner.py` read to confirm the claim matches the
code. No file outside the four exception files and this phase's own two prompt-files was written.