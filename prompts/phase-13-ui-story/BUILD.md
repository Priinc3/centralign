# BUILD — Phase 13 UI tells the story (NORMAL, after 12)

Type NORMAL (after 12 — needs the real model name + plan payload). No siblings. Phase 12 is RUNNING — do not touch its files (`src/llm/*`, `tests/test_llm_gemini*`, its planner lines). OWN: `src/ui/*`, `tests/test_ui_offline.py`. EXCEPTION (lines only): `src/ui/app.py::state()` one-line `plan_source` key fix (11 finding); `docs/USER-TEST.md` two number lines (127→133); `demo/video-script.md` ONLY the quoted UI strings this phase changes; ADDITIVE-ONLY scenario templates in `src/runtime/planner.py` heuristic section (new entries + tests, zero edits to existing logic). Nothing else.

## Context (owner order)
Current page shows buttons and statuses but teaches nothing: no what-is-this, no how-it-works, no visible AI. For an AI-employee submission the page must narrate: what the system is, the 8-stage loop lighting up live, and the model visibly planning.

## Goal
An evaluator with no context understands the build from the page alone, SEES the AI work, and watches it handle MORE than one job (generalization, not a one-trick demo).

## Deliverables (OWN only)
- Scenario gallery (owner order): 3 pre-defined runnable scenario cards above the Run button. S1 = invoice intake (default, existing flow). S2/S3 = read-side jobs using ONLY proven tools (e.g. "Audit the ERP": list posted invoices → count + total, no approval; "Summarize the invoice inbox": list seed dir → parse each → table, no approval). Each card states what it will run (tool chain in plain words) BEFORE you click. Selecting a card loads its task; stages/AI panel/evidence all follow that scenario.
- Planner coverage for all 3 (additive templates only, proven cold per scenario — no mocked plans; if a scenario can't plan honestly, replace the scenario, not the planner logic).
- Header block: what this is (1 line: AI employee for invoice intake) + `How it works` 8-stage strip (Goal→Understand→Plan→Execute→Observe→Adapt→Verify→Complete) with the live stage highlighted per poll.
- AI panel: planner badge (`heuristic offline` vs `llm:gemini/<model>` from 12), the model-returned plan (steps + per-step intent in plain words), and — on fallback — an HONEST badge (`model fallback: <reason>, deterministic planner used`) never a fake AI label.
- Keep: Run/Approve/verdict/evidence/ERP (unchanged behavior); fix `planner: undefined` (read `evidence.run.plan_source`); keep localhost-only, redaction, 500ms poll.
- Tests: stage-strip + AI badge render from state payloads (HTTP, no browser); full suite green; scan 0.
- Video-script quote refresh ONLY for strings changed above (re-verify each against live session like 11 did).

## Criteria
- Cold session narrates itself: what → stages light up → AI plan visible → approval → pass 8/8 → replayed=2 on rerun.
- All 3 scenarios cold-pass with evidence (S1 pass 8/8 + ERP 1; S2/S3 pass with read-only totals, zero approvals, zero ERP writes); switching scenarios resets state visibly.
- No mocked AI: badge source is the evidence `plan_source`, nothing else.
- `grep 127` stays empty in scope; 10's close + role line untouched; 12's files untouched.

## Parallelism gate (12 is RUNNING — read this first)
No git repo exists yet, so two writers in one file = one overwrites the other. Split:

- 🟢 START NOW (13a, zero shared files): header + stage strip + scenario gallery UI + AI-panel heuristic path + `plan_source` key fix + USER-TEST numbers + tests. Prove with heuristic sessions.
- 🔴 AFTER 12 REPORTS DONE (13b): ANY `src/runtime/planner.py` edit (scenario templates), LLM-badge wiring, `--llm` live verification, video-quote refresh for changed strings.
- Reason: 13b needs 12's final model name/payload shape, and both phases touch `planner.py`. Same-file writes → sequential, no exceptions while 12 runs.

## Order
Write `prompts/phase-13-ui-story/REPORT.md` (before/after copy, live session transcript, quote map, limits). Mark sections 13a-done vs 13b-pending explicitly.
