# REPORT — Phase 02 tools + sim app (G1)

**State: DONE.** 23/23 tools tests green (1 skipped without Playwright), 1062 lines across 10 files.
Browser path verified against a real headless Chromium; ERP idempotency verified by double POST.

## Files changed (all OWN — no sibling file touched)

| File | Lines | What |
|---|---|---|
| `src/tools/manifest_registry.py` | 102 | Loads 6 manifests through 01's frozen `ToolManifest`, dispatches by name, gates `destructive` behind `confirmed=True`, `registry()`+`callables()` for 01's Executor, `defaults()` for strict-mode args |
| `src/tools/browser_tool.py` | 118 | Playwright sync/chromium, URL allowlist (`ALLOWLIST` env), auto-wait, sandboxed screenshot, lazy import + reused browser/context |
| `src/tools/files_tool.py` | 86 | `safe_path()` chokepoint: sandboxed to `data/`, rejects absolute/`..`/`~`/symlink escapes |
| `src/tools/invoice_tool.py` | 139 | PDF text by regex (uncompressed `(...) Tj`), `Decimal` amount parse, `find_latest(company)` |
| `src/tools/erp_tool.py` | 105 | stdlib urllib POST/GET, content-derived `Idempotency-Key` (sha256), URL-encoded filters |
| `src/tools/__init__.py` | 15 | Public surface: `registry()`, `callables()`, `execute()`, `defaults()` |
| `sim_app/server.py` | 158 | stdlib `http.server` ThreadingHTTPServer + SQLite: `/invoices` POST/GET, `/invoices/<id>`, `/portal`, `/health` |
| `sim_app/schema.sql` | 15 | `invoices` table, `idempotency_key TEXT NOT NULL UNIQUE` is what makes double-POST collapse to one row |
| `data/seed/make_pdfs.py` | 91 | Regenerates the seeds as real, uncompressed PDFs (escaped literals, correct xref offsets) |
| `data/seed/invoices/*` | 3 files | 2 PDFs + 1 TXT: Company X latest, Company X older, Company Y distractor |
| `data/seed/expected.json` | 46 | Ground truth the tests assert against (exact amount/due, both distractors named) |
| `tests/test_tools_smoke.py` | 233 | 23 tests, no LLM, no network beyond the in-process sim ERP |

Runtime artifacts (not source): `data/sim_erp.db`, `data/screenshots/{portal,test-portal}.png`.

## Criteria — commands + raw output

### 1. `python sim_app/server.py --port 8901 & python -m pytest tests/test_tools_smoke.py -q`
```
sim-erp on http://127.0.0.1:8901  db=/Users/princegondaliya/Learning/.../data/sim_erp.db
.....................s.                                                  [100%]
22 passed, 1 skipped in 2.09s
```
The 1 skip is `test_browser_opens_allowlisted_localhost_page` (needs Playwright). With Playwright installed:
```
.......................                                                  [100%]
23 passed in 3.01s
```

### 2. Allowlist blocks `evil.com` (`ALLOWLIST=localhost,example.com`)
```
http://localhost:8901/portal     ALLOWED -> http://localhost:8901/portal
https://example.com/x            ALLOWED -> https://example.com/x
http://evil.com                  BLOCKED  host not on ALLOWLIST=localhost,example.com: evil.com
http://example.com.evil.com      BLOCKED  host not on ALLOWLIST=localhost,example.com: example.com.evil.com
file:///etc/passwd               BLOCKED  only http(s) URLs allowed: 'file:///etc/passwd'
javascript:alert(1)              BLOCKED  only http(s) URLs allowed: 'javascript:alert(1)'
```
`test_registry_blocks_evil_com_without_launching_browser` monkeypatches `browser_tool._context` to
raise, so the assertion proves the guard fires *before* Playwright is touched, not after.

### 3. Invoice parse ±0 error, ERP double-POST = 1 row
```
find_latest('Company X') -> matched=2, latest=INV-X-2024-0912-acme.pdf  (Company Y filtered out)
amount 4820.00 == expected 4820.00   (Decimal compare, no float)
due 2024-10-12, invoice_number CX-2024-0912, vendor 'ACME SUPPLY CO.', currency USD

post1 id=1 created=True | replay id=1 created=False | same_row=True | rows=1
```
Amount is compared as `Decimal` against `data/seed/expected.json` — exact, not tolerance-based.

### 4. Seed PDFs are real PDFs, not just my regex's opinion
```
$ pdftotext -layout data/seed/invoices/INV-X-2024-0912-acme.pdf -
ACME SUPPLY CO. (company: Company X)
INVOICE
Invoice Number: CX-2024-0912
Amount Due: USD 4,820.00
```
`test_pdf_text_matches_a_real_pdf_reader` asserts my extractor and poppler agree on the same lines.

### 5. Browser tool really drives Chromium (Playwright + chromium installed in a throwaway venv)
```
{'ok': True, 'risk': 'read', 'status': 200, 'title': 'Invoice portal'}
auto-waited text: INV-X-2024-0703-acme.pdf — 993 bytes / INV-X-2024-0912-acme.pdf — 1156 bytes / ...
screenshot: data/screenshots/portal.png 26184 bytes
close() ok
```
Screenshot visually confirmed: the portal renders with all 3 seeded invoices.

## How to verify

```bash
python3 sim_app/server.py --port 8901 &          # sim ERP on :8901
python3 -m pytest tests/test_tools_smoke.py -q   # 22 passed, 1 skipped

# browser, if you install Playwright (see Limits):
pip install playwright && python -m playwright install chromium
python3 -m pytest tests/test_tools_smoke.py -q   # 23 passed

# one-shot E2E: find latest Company X invoice -> post to ERP
ERP_URL=http://127.0.0.1:8901 python3 -c "
from src.tools import execute, defaults
A = lambda t, **g: {**defaults(t), **g}
inv = execute('invoice_find_latest', A('invoice_find_latest', company='Company X'))['latest']
print(execute('erp_post_invoice', A('erp_post_invoice', vendor=inv['vendor'], company=inv['company'],
      invoice_number=inv['invoice_number'], amount=inv['amount'], currency=inv['currency'],
      due_date=inv['due'], source_file=inv['file']))['body'])"

curl -s localhost:8901/invoices          # exactly 1 row
curl -s localhost:8901/portal            # HTML inbox the browser tool reads
```

Integration with 01 (verified, not assumed): `python -m src.runtime.loop --task "find latest invoice
from Company X and post it to the ERP" --offline` now plans against **my** tool ids
(`erp_post_invoice`, `invoice_find_latest`, `invoice_parse`) — 01's `load_registry()` preferred path
(`registry()` + `callables()`) works, so `manifests()` was not added.

## Contract conformance

01's contract is frozen and I did not touch it. My manifests use `parameters` (not `input_schema`),
ids satisfy `NAME_RE` (underscores), every property is in `required` with `additionalProperties:false`,
and they validate through `ToolManifest.model_validate` — a manifest drift raises loudly at load.
I did **not** reimplement `validate_args`; `execute()` calls 01's. Risk tiers come from the contract
(`read`/`write`/`destructive`); `erp_post_invoice` is the only `write` and sets `requires_approval`.

**Dotted ids:** 03's `context/tools.yaml` and `gate.py` key on `erp.post`, but `NAME_RE` forbids dots.
I conformed to the contract and made `resolve()` accept either spelling:
`erp.post → erp_post_invoice`, `browser.fetch → browser_open`, and `invoice.parse → invoice_parse` by
the generic dots→underscores rule. So 03's gate ids work against my tools without a contract change.
If 01 later relaxes `NAME_RE`, the alias table is the only thing to delete.

## Limits / known ceilings (each named, with the upgrade path)

1. **PDF extraction covers uncompressed streams only** — one `(...) Tj` per line. True for every PDF
   `make_pdfs.py` produces; a real vendor PDF with Flate compression returns no text. Swap the body of
   `invoice_tool.pdf_text()` for `pypdf.PdfReader(...).pages[].extract_text()`. No PDF dep is on the
   approved list, which is why it is hand-rolled.
2. **Dates are ISO-only** (`2024-10-12`). `09/12/2024` and `12-Sep-2024` will not match. Add one
   normalization regex per format in `invoice_tool.FIELDS`.
3. **Amount regex needs a label** (`Amount Due:` / `Total Due:` / `Grand Total:`). An invoice that only
   prints a bare total is not parsed. Deliberate: a wrong amount is worse than an unparsed invoice.
4. **Amount is kept as a decimal string** end to end, never a float — that is the ±0 guarantee. Consumers
   must not `float()` it.
5. **Playwright is not installed in this environment** (global Python is PEP 668 externally-managed, so
   I did not `--break-system-packages` it). I verified the browser path in a throwaway venv instead. The
   allowlist tests need no Playwright and run everywhere.
6. **Loopback is implicitly allowed** in `check_url` even on a tight `ALLOWLIST`, because `127.0.0.1`
   cannot leave the machine. Remove the `LOOPBACK` clause in `browser_tool.check_url` to forbid it.
7. **`browser.open` is one page per call and reuses one browser/context per process** — fine for the
   demo, not for concurrent runs. Per-run contexts if Phase 05 parallelizes.
8. **ERP `Idempotency-Key` is content-derived** (sha256 of the payload): the same invoice is one row
   forever, so a *corrected* re-post with a changed amount creates a second row by design.
9. **`sim_app` binds `127.0.0.1` by default** and has no auth — it is a local stand-in for an ERP, not one.
10. **A venv is not set up for this repo.** `pytest` needs the repo root on `sys.path`; my test file does
    a 2-line `sys.path.insert` rather than creating `tests/conftest.py`, which all three phases would
    otherwise race to write. A shared `tests/conftest.py` is probably right for B2 — that is a CEO call.
11. **Manual JSON Schema validation is 01's `validate_args`**, not mine — I deleted my own copy when I
    found theirs. My manifests only use keywords it implements.

## Bugs found and fixed during this build (worth knowing)

- `data/seed/make_pdfs.py` originally wrote raw `(` `)` inside PDF string literals. Poppler tolerated it,
  my extractor did not, and line 1 of every seed PDF was silently lost (`vendor` became `INVOICE`).
- My unescape map was applied to whole extracted lines instead of the escape sequences, zeroing every
  PDF line. Both bugs were only visible because the tests assert on parsed fields, not on "it ran".
- `browser_tool.close()` crashed with `NoneType is not callable`: after `sync_playwright().start()`,
  `Playwright.stop` routes to a `__exit__` with no exit function. Fixed by keeping the context manager
  and exiting it explicitly.
- `erp_tool.list_invoices` did not URL-encode the filter, so `?company=Company X` raised `InvalidURL` —
  caught by the E2E replay, not by the unit test. Regression test added.
- Strict mode sends `""` (not a missing key) for optional args, so `args.get(k, default)` never fires.
  Handlers use `args.get(k) or default`.

## Help needed

- **01/04 (blocking for the B1 TEST, not for my deliverables):** `Executor` records a step `succeeded`
  whenever a tool returns a dict, so `{ok: false, status: 422}` looks green in evidence. Suggest
  `StepResult.ok` also requires `result.get("ok", True)`. One line in `src/runtime/executor.py`, which
  is 01's file — I did not edit it.
- **01 (quality):** the offline heuristic planner fills *every* string property with the whole task text,
  so `invoice_find_latest` receives `dir="Company X and post it to the ERP"`. My tool correctly fails it
  (`FileNotFoundError: not a directory`), but the demo needs arg-aware planning or explicit heuristics.
- **03:** confirm your `context/tools.yaml` mirror uses my contract-legal ids, or rely on `resolve()`.
  Your `browser.fetch` and `erp.post` ids already resolve; `files.write` has no counterpart (I ship
  `files_read`/`files_list` — the invoice flow never writes a file).
- **CEO:** approving `pypdf` would close Limit 1. Everything else ships as-is.

**BLOCKED BY:** nothing. Contracts landed mid-build (11:44) and I conformed on the first full run.
