# FIX-1 — Phase 05 demo-ux (B2 polish F3/F4/F5)

Scope locked: `src/cli/main.py`, `src/cli/doctor.py`, `tests/test_demo_offline.py` only. DO NOT touch engine files. Update `prompts/phase-05-demo-ux/REPORT.md` (append FIX-1).

## F4 — `--queue` help lies (low)
`src/cli/main.py:548`: help `default: context/company.yaml` → `default: data/gate.jsonl (from company.yaml approval.queue)`.

## F3 — rejected input litters repo (low)
`run --task ""` (and any `blocked`-before-plan path) writes `runs/<id>/` into repo tree. Fix: route `run` blocked-empty runs to scratch (`--runs` default honoured; when default repo `runs/` would be used and verdict is blocked-empty, write under `$TMPDIR`/tmp instead and print path). Keep gitignored either way. Test: empty run leaves no new dir under repo `runs/`.

## F5 — doctor sim note confuses (info)
`src/cli/doctor.py:130`: `demo` binds free port per run, so `not running at :8901` note reads like failure after success. Fix wording: `sim ERP note not running at :8901 — fine: the demo starts its own per run`. Keep exit 0.

## Verify-with
- `python3 -m pytest tests/test_demo_offline.py -q` + full suite green.
- `rm -rf /tmp/fx && bash demo/run.sh /tmp/fx` pass 8/8; `python3 -m src.cli.main run --task ""` blocked rc=1 with no new repo `runs/` dir; `--queue --help` shows gate.jsonl; `doctor` line reworded.
