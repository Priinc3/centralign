# BUILD — Phase 10 intern positioning (NORMAL, docs-only)

Type NORMAL. No siblings. Owner decision: applying as **AI Engineering Intern**. Demo presents intern scope; founding breadth is the closing beat, not the headline.

EXCEPTION (CEO-granted, docs only): you may edit ONLY `SUBMISSION.md` (role line + checklist framing) and `demo/video-script.md` (closing beat). DO NOT TOUCH anything else. Read-only: all REPORTs, `docs/USER-TEST.md`.

## Goal
Evaluator never wonders which role: packet says Intern everywhere, video ends with founding upside.

## Deliverables
1. `SUBMISSION.md`: top role line `Role: AI Engineering Intern (prototype also demonstrates Founding-scope architecture — see video close)`; keep criterion mapping untouched (shared criteria).
2. `demo/video-script.md`: closing beat (~10s): "Built as my Intern submission — narrow invoice flow, genuinely autonomous; the same runtime also carries the Founding-scope pieces: contracts, ledger, verifier, multi-key router — happy to go deep there live." Must stay truthful (all named pieces exist + tested).
3. Form field in USER-STEPS: role tick = Intern (note in REPORT if USER-STEPS needs the word; USER-STEPS is prompt-file — edit it too, allowed).

## Criteria
- `grep -in "founding" SUBMISSION.md demo/video-script.md` → each file names Intern first, founding second.
- No engine/test/doc-number churn; suite untouched.

## Order
Write `prompts/phase-10-intern/REPORT.md` (lines changed, quotes, verify greps).
