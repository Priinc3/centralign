# BUILD — Phase 08 submission close-out (NORMAL, last gate before form)

Type NORMAL (after 07). No siblings. EXCEPTION (CEO-granted, docs only): you may edit ONLY `README.md`, `SUBMISSION.md`, `demo/script.md`, `demo/video-script.md` (owners 05/06 — this is a scoped refresh, no engine files, no other docs). DO NOT TOUCH anything under `src/`, `tests/`, `scripts/`, `docs/`, `context/`, `sim_app/`, `data/`. Read-only: all REPORTs/VERIFYs, `docs/USER-TEST.md`.

## Context
Engine DONE (127 passed). Packet blocked: no git repo, no video (both USER actions), stale `114→127` in 6 places, over-stated LLM claim, pre-ticked URL checklist.

## Goal
Every claim in the packet matches a fresh run; everything the user must do by hand is a copy-paste checklist.

## Deliverables (exception files only)
1. Numbers refresh: `114→127` at `README.md:49,199,208`, `SUBMISSION.md:10,46`, `demo/video-script.md:98` — each verified against `python3 -m pytest tests/ -q` run NOW (paste count in REPORT).
2. Honest LLM claim: README Models table + SUBMISSION mapping state — offline heuristic proven (8/8); multi-key router + 429 failover proven live AND in tests; full live plan-shape on Gemini falls back by design (F2) and OpenAI-key path unexercised — say exactly that, no more.
3. SUBMISSION checklist un-tick URL items (`- [ ]` until URLs real) + add lines 7–8 `GITHUB_URL: <fill after push>` / `VIDEO_URL: <fill after upload>`.
4. `demo/video-script.md`: re-verify every quoted line against a fresh `bash demo/run.sh /tmp/vid` + append run; fix drift (counts, timings, replayed=). Append `RECORDING.md` section IN the script file: terminal 110×32, clear, one-take order (cold → append → evidence head → scan → suite), narrate beats, 75–90s, cuts allowed (evidence beat first, never approval/replay beats), upload unlisted + paste URL into SUBMISSION.
5. `docs`-adjacent: create `prompts/phase-08-submission/USER-STEPS.md` (prompt-file, allowed): copy-paste git block (`git init -b main; git add -A; git commit; gh repo create centralign-operator --public --source=. --push` + fallback manual-remote commands + `git remote -v` check), video upload steps, form-field list, final `pytest+scan+demo` triple to run post-push from the clone.

## Criteria
- `grep -rn "114 passed" README.md SUBMISSION.md demo/` → empty; `grep -rn "127 passed" README.md SUBMISSION.md demo/video-script.md` → 6 hits.
- No `strict tool-calling` promise without the fallback sentence in the same paragraph.
- Fresh demo triple pasted in REPORT matches script quotes; USER-STEPS commands dry-checked (flag any that need the user's GitHub name).

## Order
Write `prompts/phase-08-submission/REPORT.md` (files changed with line refs, cmds+raw output, remaining USER actions). Out of scope: per-provider schema (F2/Phase 09, post-submit optional).
