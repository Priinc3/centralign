# Batch B2 TEST — 04+05+06 integration (reliability×demo×security)

Scope: 3 NORMAL phases. Builder: run ALL, paste RAW output into `prompts/batch-B2-TEST-RESULT.md`.

## 0. Setup
```bash
python3 -m pytest tests/ -q
rm -rf /tmp/b2t && bash demo/run.sh /tmp/b2t
```

## 1. Happy + replay + resume
```bash
bash demo/run.sh /tmp/b2t --append
python3 -m src.cli.main doctor
ERP_URL=http://127.0.0.1:8902 python3 -m src.reliability.checkpoint --help | head -5
```

## 2. Edges
- E1 empty: `python3 -m src.cli.main run --task ""` → blocked rc=1.
- E2 downed ERP: stop sim, run demo task via CLI to scratch `--runs /tmp/b2t-down`, expect fail rc=1 with retry events; restart sim, `--resume` → pass, ERP count 1.
- E3 double approval: approve same request twice → second refused (already-closed).

## 3. Security + publish
```bash
python3 -m src.security.scan
python3 -m pytest tests/test_security_hardening.py -q
git init -q /tmp/gi2 2>/dev/null; GIT_DIR=/tmp/gi2/.git GIT_WORK_TREE=. git add -An 2>/dev/null | grep -E "runs/|\.db$|\.jsonl$|\.env" || echo "publish-clean"
```

## 4. Cross-phase (04×05×06)
```bash
python3 -c "import json,sqlite3; c=sqlite3.connect('/tmp/b2t/runs/_ledger.sqlite3'); rid=c.execute('SELECT run_id FROM runs ORDER BY created_at DESC LIMIT 1').fetchone()[0]; e=json.load(open(f'/tmp/b2t/runs/{rid}/evidence.json')); print(e['verdict']['status'], e['verdict']['summary']); print('plan_source:', e['run'].get('plan_source')); print('totals:', e.get('totals'))"
```

## 5. Write `prompts/batch-B2-TEST-RESULT.md` (cmds+raw output, pass/fail, findings, env).
