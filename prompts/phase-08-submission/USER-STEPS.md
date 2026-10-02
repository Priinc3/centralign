# USER-STEPS — the four things only you can do (Phase 08 close-out)

Everything below is a copy-paste block. Three of the four are GitHub/video actions no code change
can perform for you; the fourth is the re-check that proves the pushed clone actually runs.

**State as of the phase-08 build:** engine DONE (`127 passed, 1 skipped`), `findings: 0` on the
security scan, no git repo yet, no video yet. Both URL lines in `SUBMISSION.md` are still
`<fill after …>` placeholders and their checklist boxes are unticked on purpose.

**The only things you must type yourself:** your GitHub handle (below) and the video file path.
`gh` is already installed and logged in as **`Priinc3`** on this machine — confirmed, so if that is
not the account you want the submission under, log into the right one first
(`gh auth switch` / `gh auth logout`).

---

## 1. Push the repo to GitHub (nothing exists remotely yet)

There is no `.git` in this directory. Run from the project root:

```bash
cd /Users/princegondaliya/Learning/Projects/temp/Draft/centralign
git init -b main
git add -A
git commit -m "CentrAlign: an AI operator for invoice intake — offline demo, approval-gated, evidence-backed"
gh repo create centralign-operator --public --source=. --push
```

Then **check** it landed, and copy the URL it prints:

```bash
git remote -v
gh repo view --json url -q .url
```

- `origin` should read `https://github.com/Priinc3/centralign-operator.git` (or your handle).
- If `git remote -v` prints **nothing**, the push did not happen — do not continue to step 3.
- Expected URL: `https://github.com/Priinc3/centralign-operator`
  → paste it into `SUBMISSION.md` line 7 as `GITHUB_URL: https://github.com/Priinc3/centralign-operator`.

**Fallback, if `gh repo create` fails** (no `gh`, or you want the remote by hand):

```bash
git init -b main
git add -A
git commit -m "CentrAlign: an AI operator for invoice intake — offline demo, approval-gated, evidence-backed"
# create an EMPTY public repo named centralign-operator at https://github.com/new first, then:
git remote add origin https://github.com/Priinc3/centralign-operator.git
git push -u origin main
git remote -v
```

**What is deliberately not pushed** (`.gitignore` already excludes it, no action needed): `runs/`,
`*.db`, `*.jsonl` (the approval queue `data/gate.jsonl`), `.env*`, `__pycache__/`, `.pytest_cache/`,
`.DS_Store`. Verified before writing this file: no `.env` in the tree, and no key-shaped string in
`README.md` / `SUBMISSION.md` / `prompts/` / `docs/` / `demo/` / `context/`.

---

## 2. Record and upload the video

The shoot — terminal 110×32, `clear`, one take, 75–90s, in this order: cold run → append run →
evidence → scan → suite — is written out as `RECORDING.md` at the bottom of
[`demo/video-script.md`](../../demo/video-script.md). Read that section; it has the keystroke table
and what may be cut.

Upload the file **unlisted** (anyone with the link, not listed on your profile):

- YouTube → upload → visibility **Unlisted** → copy the share link.
- or Drive → upload → Share → *Anyone with the link* → Viewer → copy the link (or use
  `https://drive.google.com/file/d/<id>/preview` if a direct play link is required).

Then paste it into `SUBMISSION.md` line 8 as `VIDEO_URL: <paste>`, and tick both boxes at the
bottom of `SUBMISSION.md` (the GitHub link and the Video lines).

---

## 3. Fill the submission form

Fields to fill, with what goes in each — nothing here is invented, all of it is in the repo:

| form field | value / where to find it |
|---|---|
| **Role applied for** | **`AI Engineering Intern`** — tick this one. The packet is framed as the Intern submission (`SUBMISSION.md` line 3); the Founding Engineer role exists at the same company, but the prototype and this submission are the Intern scope. Only switch it if you change your mind about which role you are applying for. |
| Repo URL | `https://github.com/Priinc3/centralign-operator` (step 1) |
| Video URL | the unlisted link from step 2 |
| One-line pitch | *"An AI operator that turns 'find the latest invoice from Company X and post it to the ERP' into a verified, approval-gated, evidenced completion — in 0.4s, offline, with no API key."* (`SUBMISSION.md` head) |
| Run it in one command | `bash demo/run.sh` → `verdict: pass 8/8` and `ERP count: 1` |
| Proof / tests | `python3 -m pytest tests/ -q` → `127 passed, 1 skipped`; `python3 -m src.security.scan` → `findings: 0` |
| Architecture | README → *Architecture* (diagram + per-stage table); per-phase reasoning in `prompts/*/REPORT.md` |
| Limits / what is faked | README → *Limits — stated, not hidden*; `SUBMISSION.md` → *Honest limits* |
| Scope honesty note | `SUBMISSION.md` → *The narrow-genuine statement* (one workflow, one company profile, nothing mocked on the demo path) |
| LLM claim | `SUBMISSION.md` → *What the LLM path has actually been exercised on* — read it before writing anything about the model |

If the form asks "what would you build next", README → *What is next* has the five items, already
ranked, with the reason for each. If it asks a role-specific question, answer it as the **Intern**
applicant — engineering ability, speed of learning, experimentation, technical understanding (the
intern discussion emphasis); the architecture/scalability/security framing is the Founding track,
which is one optional line in the video close, not the submission's headline.

---

## 4. Re-check from a clean clone (do this after the push, before you submit)

This is the step that catches "it worked on my machine" — a fresh clone of the *pushed* repo,
run in a temp dir, so nothing here can be the stale local state. It is the triple that proves an
evaluator gets what you got:

```bash
cd /tmp && rm -rf centralign-verify && git clone --depth 1 https://github.com/Priinc3/centralign-operator centralign-verify
cd /tmp/centralign-verify
python3 -m pytest tests/ -q            # expect: 127 passed, 1 skipped
python3 -m src.security.scan           # expect: findings: 0  → safe to publish
bash demo/run.sh                       # expect: verdict: pass 8/8  replayed=1  plan: heuristic  ·  ERP count: 1
```

Read the three expectations before you run it — if any line differs, stop and fix the repo rather
than the form. `demo/run.sh` needs no install and no key; the suite needs `requirements.txt`
(`python3 -m pip install -r requirements.txt`) if the fresh machine lacks pytest/pydantic.

---

## Remaining hand-offs, in one list

1. `git init` + `commit` + `gh repo create … --push` (step 1) → paste `GITHUB_URL` into `SUBMISSION.md`.
2. Record per `demo/video-script.md` §RECORDING.md → upload unlisted (step 2) → paste `VIDEO_URL`.
3. Fill the form (step 3).
4. Re-check from a clean clone (step 4).

Nothing above is blocked on further code work — the engine, docs, demo and scan are all green as of
this phase. The only open engineering question is deliberately parked as post-submit: the
per-provider tool schema for Gemini (finding F2 in `prompts/phase-07-user-acceptance/REPORT.md`),
where `--llm` falls back to the heuristic plan by design. See also `docs/USER-TEST.md` for the
manual acceptance runbook (read-only this phase).