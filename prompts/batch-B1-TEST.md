# Batch B1 TEST — G1 integration (01+02+03)

Scope: 1 parallel group. Goal: `invoice intake` E2E genuinely works offline with policy gate + evidence. Builder: run ALL cmds below, paste RAW output into `prompts/batch-B1-TEST-RESULT.md`. No summary without output.

## 0. Setup
```bash
python3 -m pytest tests/test_runtime_smoke.py tests/test_tools_smoke.py tests/test_memory_policy.py -q
python3 sim_app/server.py --port 8901 &
sleep 1; curl -s localhost:8901/health
```

## 1. Happy path (must pass)
```bash
ERP_URL=http://127.0.0.1:8901 python3 -c "
from src.tools import execute, defaults
A = lambda t, **g: {**defaults(t), **g}
inv = execute('invoice_find_latest', A('invoice_find_latest', company='Company X'))['latest']
print('LATEST:', inv['file'], inv['amount'], inv['due'])
r = execute('erp_post_invoice', A('erp_post_invoice', vendor=inv['vendor'], company=inv['company'], invoice_number=inv['invoice_number'], amount=inv['amount'], currency=inv['currency'], due_date=inv['due'], source_file=inv['file']))
print('POST:', r['body'])
r2 = execute('erp_post_invoice', A('erp_post_invoice', vendor=inv['vendor'], company=inv['company'], invoice_number=inv['invoice_number'], amount=inv['amount'], currency=inv['currency'], due_date=inv['due'], source_file=inv['file']))
print('REPLAY same_row:', r['body']==r2['body'])
"
curl -s localhost:8901/invoices
python3 -m src.runtime.loop --task "find latest invoice from Company X and post it to the ERP" --offline --tools auto
cat runs/*/evidence.json | python3 -c "import json,sys,glob; e=json.load(open(sorted(glob.glob('runs/*/evidence.json'))[-1])); print('verdict:', e['verdict']); print('predicates:', [(p['statement'][:40], p['passed']) for p in e['verdict']['predicates']])"
```

## 2. Top-3 edges
- E1 empty task: `python3 -m src.runtime.loop --task "" --offline --tools demo` → must NOT crash, verdict fail/blocked with plain words.
- E2 double-submit: POST same invoice twice (see happy) → `rows=1`, second `created=False`.
- E3 offline no-key: `env -u OPENAI_API_KEY python3 -m src.runtime.loop --task "demo" --offline --tools demo` → completes, `plan_source=heuristic`, rc=0, <2s.

## 3. Security probes (all must hold)
```bash
python3 -m src.policy.gate --tool erp.post --amount 999999   # expect approve
python3 -m src.policy.gate --tool erp.post --amount 10       # expect allow
python3 -m src.policy.gate --domain evil.com                 # expect deny, exit 2
python3 -c "
from src.tools.browser_tool import check_url; import os
os.environ['ALLOWLIST']='localhost,example.com'
for u in ['http://localhost:8901/portal','https://example.com/x','http://evil.com','http://example.com.evil.com','file:///etc/passwd','javascript:alert(1)']:
  try: print(u, '-> ALLOW', check_url(u))
  except Exception as e: print(u, '-> DENY', str(e)[:80])
"
python3 -c "
from src.tools import execute, defaults
try: print(execute('files_read', {**defaults('files_read'), 'path':'../../etc/passwd'}))
except Exception as e: print('TRAVERSAL BLOCKED:', type(e).__name__, str(e)[:80])
"
grep -rniE "sk-[a-zA-Z0-9]{10,}|password *= *['\"][^'\"]+['\"]|bearer " src/ sim_app/ context/ || echo "NO SECRETS"
python3 -c "import json,glob; e=json.load(open(sorted(glob.glob('runs/*/evidence.json'))[-1])); s=json.dumps(e); print('REDACT-LEAK:' if 'sk-' in s else 'EVIDENCE CLEAN')"
python3 -c "from src.contracts.tools import ToolManifest; m=ToolManifest.model_validate({'name':'erp.post','description':'x','parameters':{'type':'object','properties':{},'required':[],'additionalProperties':False}}); print('DOTTED-NAME OK:', m.name, '->', m.api_name())"
```

## 4. Cross-phase integration (G1 contract clash check — corrected APIs v2)
```bash
python3 -c "
from src.tools import registry
from src.policy.loader import load_context
from src.policy.gate import decide
from src.memory.store import Store
from src.memory.recall import recall
reg = registry(); print('tools:', sorted(reg.keys()))
ctx = load_context()
print('gate erp.post/10:', decide(tool='erp.post', amount=10.0, context=ctx).verdict)
print('gate browser evil:', decide(tool='browser.fetch', domain='evil.com', context=ctx).verdict)
s=Store(':memory:'); s.add_company('c1','Company X'); s.remember('c1','acme_payment_terms','terms','net 30 billing contact a@b.com'); print('recall:', recall(s,'c1','invoice payment terms')[:1])
"
# ok:false must NOT look green (02 HELP) — real Executor(ledger, run_id, manifests, callables), fn(**args):
python3 -c "
from src.runtime.executor import Executor
from src.ledger.store import Ledger
from src.contracts.tools import ToolManifest
import uuid
m = ToolManifest.model_validate({'name':'t','description':'x','parameters':{'type':'object','properties':{},'required':[],'additionalProperties':False},'risk':'read'})
led = Ledger(':memory:'); rid = uuid.uuid4().hex[:12]
ex = Executor(led, rid, {'t': m}, {'t': lambda **a: {'ok': False, 'status': 422, 'body': 'bad'}})
r = ex.run_step(type('S', (), {'id':'s1','tool':'t','args':{},'depends_on':[]})())
print('ok:false ->', r.status, '(must be failed, not succeeded)')
"
```

## 5. Write result
Write `prompts/batch-B1-TEST-RESULT.md` with: each cmd + RAW output, pass/fail per section, findings list, env note (python3, playwright present/absent).
Kill sim: `pkill -f "sim_app/server.py" || true`.
