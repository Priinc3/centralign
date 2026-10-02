# BUILD — Phase 11 video-on-UI rewrite (NORMAL, docs-only)

Type NORMAL, runs AFTER 10 (both touch `demo/video-script.md` — read `prompts/phase-10-intern/REPORT.md` first and keep its closing beat + role line intact). No siblings. EXCEPTION (docs only): edit ONLY `demo/video-script.md` (full rewrite to UI), `README.md` (UI run section + `127→133`), `SUBMISSION.md` (numbers only, keep 10's role line). DO NOT TOUCH anything else. Read-only: 09 REPORT (UI transcript + screenshot descriptions), 10 REPORT, USER-STEPS.

## Context
09 shipped a localhost dashboard (Run → approval card → verdict banner → evidence → ERP row). The video re-records on the UI: camera watches clicks, terminal only opens/closes the show.

## Goal
A shootable UI beat sheet where every quoted line matches today's UI + suite.

## Deliverables
1. `demo/video-script.md` rewritten: beats — (1) terminal `python3 -m src.ui.app --port 0` + URL print (~5s), (2) browser open, Run click, steps appear (~15s), (3) approval card Approve click (~10s), (4) green `pass 8/8 replayed=1` + ERP 1 row + evidence panel (~10s), (5) Run again → `replayed=2` nothing posted (~10s), (6) terminal tail: scan 0 + suite `133 passed, 1 skipped` (~10s), (7) 10's Intern close (~10s). Keep 75–100s. Every quote verified against a live UI session (drive via HTTP like 09's tests if no display; describe where the camera points per beat). Keep §RECORDING.md updated (screen-record tool, 1280×800 browser, mic beats).
2. Numbers: `127→133` everywhere 08 listed + anything quoting UI (grep to confirm zero `127` remains in publishable docs).
3. `README.md`: replace/augment terminal quickstart with UI-first run (terminal stays as alt path).

## Criteria
- `grep -rn "127 passed\|127 tests" README.md SUBMISSION.md demo/` → empty (allow 08's historical appendix ONLY if already labeled as such — else refresh).
- Each script quote traceable to 09 REPORT transcript or a fresh run pasted in REPORT.
- 10's role line + closing beat byte-identical in meaning.

## Order
Write `prompts/phase-11-video-ui/REPORT.md` (quotes↔run mapping, greps, USER record steps). Out of scope: code, F2 schema, F3.
