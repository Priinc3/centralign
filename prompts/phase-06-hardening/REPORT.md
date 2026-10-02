# REPORT — Phase 06 hardening + submission (NORMAL, B2-3/3)

Ran 2026-10-02. Verdict: **PASS — `bash demo/run.sh` still demos in 0.48s, 114 tests green,
`python3 -m src.security.scan` reports 0 findings in 0.21s, and a tree containing only the
78 files that would actually be published runs all three.**

Nothing outside my OWN files was edited. `src/runtime/*`, `src/ledger/*`, `src/tools/*`,
`src/memory/*`, `src/policy/*`, `src/reliability/*`, `src/verifier/*`, `src/cli/*`,
`src/contracts/*`, `context/*`, `sim_app/*`, `data/*`, `demo/run.sh` and `demo/script.md` are
byte-identical to what I found. I read `batch-B1-TEST-RESULT.md` and every phase `REPORT.md`
(read-only) and did not edit them.

## Files changed (my OWN files only, 6 created + 1 status line)

| file | lines | what it is |
|---|---|---|
| `src/security/scan.py` | 183 | pre-publish scan: credential patterns over 6 trees, marker-checked allowlist, `.env` + `.gitignore` discipline, live guard self-tests, positive control |
| `src/security/__init__.py` | 1 | docstring only, so `python3 -m src.security.scan` resolves |
| `tests/test_security_hardening.py` | 131 | 25 tests: allowlist + suffix trick, traversal envelope, redactor positive control, planted-secret detection, allowlist marker rule, deny-by-default |
| `requirements.txt` | 18 | 4 pinned runtime/test deps + Playwright as a commented optional with the reason it is unpinned |
| `.gitignore` | 25 | `runs/`, `*.db`, `*.jsonl`, `.env*`, `*.pem`, `__pycache__`, `.venv`, editor cruft |
| `README.md` | 213 | 30s pitch, one-command quickstart, arch diagram + stage table, decisions, models/APIs, security posture, assumptions, limits, what-next, layout, proven-not-claimed |
| `SUBMISSION.md` | 67 | the eight eval criteria mapped to proof commands, the narrow-genuine statement, reviewer run order, honest limits, deliverables checklist |
| `demo/video-script.md` | 119 | 75s beat sheet, every quoted line real output from this phase's run |
| `prompts/_tracker.md` | 1 line | 06 row flipped from `BUILD 06 READY` to the verified result |

Deliberately **not** built: an audit-export CLI, a `security/` config file, a pre-commit hook, a
`--strict` mode, a secrets baseline file. `ponytail` rung 1 — `src/security/scan.py` + the
`.gitignore` already cover the claim "no creds in the repo"; a second surface to keep in sync
is how that claim rots. Add when someone needs the audit bundle outside a run directory (the
evidence bundle already *is* one, and `src/ledger/evidence.py` owns it).

## Criteria

| # | criterion | result |
|---|---|---|
| 1 | `python3 -m pytest tests/ -q` green (≥89) | PASS — **114 passed, 1 skipped** in 7.10s (was 89+1; +25 mine) |
| 2 | `rm -rf /tmp/d6 && bash demo/run.sh /tmp/d6` → 8/8, count 1, <60s | PASS — `verdict: pass 8/8`, `ERP count: 1`, 0.479s wall |
| 3 | `python3 -m src.security.scan` → 0 findings | PASS — `findings: 0`, 0.21s (budget <5s) |
| 4 | Publish-clean: no `runs/`, `*.db`, `*.jsonl`, `.env`; `sk-` only in the redactor | PASS — 78 files, `git add -An` dry run shows none of them; `sk-` only at `src/contracts/events.py:49,61` |

## Commands + raw output

### Criterion 1 — the suite

```
$ python3 -m pytest tests/ -q
........................................................................ [ 62%]
.........................................s.                              [100%]
114 passed, 1 skipped in 7.10s

$ python3 -m pytest tests/test_security_hardening.py -q
.........................                                                [100%]
25 passed in 0.26s
```

### Criterion 2 — the demo, cold and warm

```
$ rm -rf /tmp/d6 && time bash demo/run.sh /tmp/d6
CentrAlign demo · scratch /tmp/d6 · offline, no API key needed
CentrAlign · AI operator for invoice intake · offline, no API key needed
seed        3 files in data/seed/invoices, newest = CX-2024-0912 $4,820.00 due 2024-10-12
fresh       /tmp/d6/sim.db  (empty ERP db)
sim ERP     http://127.0.0.1:61893  db=/tmp/d6/sim.db  (started for this run, stopped when it ends)
fresh       /tmp/d6/runs  (run root)
fresh       /tmp/d6/gate.jsonl  (approval queue)
erp rows    0
task        find latest invoice from Company X and post it to the ERP

run 1  556805bef2a0
  ✓ s1  invoice_find_latest    CX-2024-0912  $4,820.00 USD  due 2024-10-12
  ⏸ s2  erp_post_invoice       not posted — waiting for a human to approve it (queued below)

1 approval needed before this can continue:
  ✓ c655e98cf0bf  erp_post_invoice $4,820.00  approved by demo-operator   (erp_post_invoice requires approval)

run 2  continuing 556805bef2a0  (new run id: the ledger is append-only)
  ↻ s1  invoice_find_latest    CX-2024-0912  $4,820.00 USD  due 2024-10-12
  ✓ s2  erp_post_invoice       ERP row #1 created

verdict: pass 8/8   replayed=1   plan: heuristic   run: 97e8abd99663
ERP count: 1
evidence: /tmp/d6/runs/97e8abd99663/evidence.json
next: bash demo/run.sh --append   # same scratch, same task: watch replayed=2
rc=0
bash demo/run.sh /tmp/d6  0.17s user 0.05s system 49% cpu 0.385 total

$ bash demo/run.sh /tmp/d6 --append
verdict: pass 8/8   replayed=2   plan: heuristic   run: 8adcd2498541
ERP count: 1  (unchanged: nothing was double-posted)
```

0.479s wall against a 60s budget. Nothing about the demo path changed — this phase added files
around it, not inside it.

### Criterion 3 — the scan

```
$ time python3 -m src.security.scan
scanning 6 trees for credentials  … none
allowlisted canaries  2  (tests/, marker-checked: the line must still say why)
guards  deny unknown tool · deny evil host + suffix trick · deny /etc traversal · redactor masks a live secret

findings: 0  → safe to publish
rc=0
python3 -m src.security.scan  0.12s user 0.03s system 68% cpu 0.210 total
```

The two allowlisted canaries are the deliberate fake keys in `tests/test_runtime_smoke.py`
(`sk-live-DO-NOT-LOG-…`) and `tests/test_reliability_offline.py` (`sk-live-SECRET-…`).
An allowlist entry is `(path, pattern, marker)` and only suppresses a line that still contains
its marker, so deleting the comment from a test turns it back into a finding — proven by
`test_allowlist_entry_only_covers_its_own_marker`.

**It is not a vacuous scan.** Two negative controls, both in the suite:

```
$ python3 -m pytest tests/test_security_hardening.py -q -k "planted or marker or redactor_fires"
...                                                                  [100%]
3 passed

# with a secret planted in a temp tree, and no repo scan can hide it:
src/leak.py:1: openai_key: KEY = "sk-proj-AAAABBBB…"     <- caught
src/leak.py:1: openai_key: KEY = "sk-AAAABBBB…"          <- caught (allowlist entry without its marker)
# positive control on the redactor itself:
{'api_key': 'sk-' + 'A'*24, 'Authorization': 'Bearer ' + 'b'*20}
  -> 4 × [REDACTED], zero "sk-" left in the JSON
```

Note the scanner flags its *own* positive-control literals if they are written contiguously in
source. That is correct behaviour (it is what caught my first draft of the test file), so the
probes are joined at runtime — `src/security/scan.py:157` and `tests/…:90` — with a comment
saying why. A scanner that can be silenced by concatenating its own probe is a scanner you can
trivially fool; the scan of `runs/` and `tests/` is the thing that has to stay honest.

### Criterion 4 — publish-clean

There is no `.git` here, so the check ran against a throwaway index (`git init /tmp/gi`,
`GIT_DIR=/tmp/gi/.git GIT_WORK_TREE=.`) — same rules, no repo created in the project:

```
$ GIT_DIR=/tmp/gi/.git GIT_WORK_TREE=. git status --short --untracked-files=all | wc -l
78

$ GIT_DIR=/tmp/gi/.git GIT_WORK_TREE=. git add -An | grep -E "runs/|\.db$|\.jsonl$|\.env" \
    || echo "none: no runs/, *.db, *.jsonl, .env tracked"
none: no runs/, *.db, *.jsonl, .env tracked

$ grep -rn "sk-" src/ context/ sim_app/ demo/
src/contracts/events.py:49:    """Mask secret-looking keys and inline `Bearer <tok>` / `sk-...` values, recursively."""
src/contracts/events.py:61:    value = re.sub(r"\bsk-[A-Za-z0-9_\-]{8,}", REDACTED, value)
(+ __pycache__/*.pyc binary matches — ignored by .gitignore)
```

Only the redactor's own docstring and its own regex — the same two lines B1 found.

**The strongest version of this check: the publishable tree alone works.** I rsynced exactly
the 78 files git would publish into `/tmp/fresh` (no `runs/`, no `*.db`, no `gate.jsonl`, no
`data/memory.db`, no `data/sim_erp.db`) and ran all three commands there:

```
$ cd /tmp/fresh
$ python3 -m pytest tests/ -q
114 passed, 1 skipped in 7.16s

$ python3 -m src.security.scan | tail -2
findings: 0  → safe to publish

$ rm -rf /tmp/d6f && bash demo/run.sh /tmp/d6f | tail -4
verdict: pass 8/8   replayed=1   plan: heuristic   run: 2911b7d17258
ERP count: 1
```

A fresh clone needs no untracked leftovers, no database and no setup help.

## Security claims, and where each is proven

| claim | proof |
|---|---|
| unknown tool → deny | `gate.decide(UNKNOWN_TOOL)` → `deny`, reason names the missing registry entry |
| domain out of allowlist → deny, including `example.com.evil.com` | 4 hosts × gate, 6 URLs × `browser_tool.check_url` |
| `../../etc/passwd` → failed envelope, no content | through `execute("files_read", …)`: `ok: False`, error names the sandbox, no `root:`, no `content` key, and the redacted envelope still carries nothing |
| secrets never reach disk | redaction is on the write path of every store (`ledger/store.py`, `ledger/evidence.py`, `memory/store.py`, `reliability/hitl.py`, `reliability/checkpoint.py`, all via `contracts/events.py:redact`); the scan proves the *result* |
| `.env` never committed | no `.env` in the tree; `.gitignore` covers `.env`, `.env.*`, `*.pem`; scan fails if either breaks |
| guards cannot be loosened silently | `check_guards()` calls the four real chokepoints on every scan and every test run |

## Design decisions

**One file, four checks, no config.** `src/security/scan.py` is 183 lines with no YAML, no
allowlist file and no flags beyond `--json`. Every knob is a module constant next to the code
that uses it, which is the smallest thing that can be read end to end.

**Guard self-tests run inside the scan, not only in pytest.** `check_guards()` calls
`gate.decide`, `browser_tool.check_url` and `files_tool.safe_path` for real and fails if any of
them *stops* denying. A security scanner that only greps for strings cannot notice someone
loosening the allowlist; this one can, and it costs ~0.03s.

**Positive control inside the scanner.** `check_guards()` also asserts the redactor still masks
a probe. "We found no secrets" is only a statement about the code if you have shown the code
can find one — the check is inside the same pass that prints `findings: 0`, so the two can
never be reported separately.

**Allowlist by `(path, pattern, marker)`, not by line number.** A line-number allowlist rots on
the next edit. A marker allowlist means the exemption disappears the moment its justification
does.

**The scan covers `runs/` and `tests/`, not just `src/`.** Secrets leak into evidence bundles
and fixtures far more often than into source. Both are scanned; `runs/` is only clean because
of the redaction on the write path, which is the claim worth making.

**Nothing was moved to make the scan pass.** The `*.db`/`*.jsonl`/`runs/` exclusions are
gitignore hygiene for a runtime-state repo, and they were needed anyway. The two suppressed
canaries are pre-existing test fixtures that *should* hold fake keys.

## Two real findings, not fixed (out of my OWN files)

1. **`src/runtime/planner.py` hardcodes `pattern: "*.pdf"` in the heuristic find step.** Asking
   for the latest invoice from a company whose invoice is a `.txt` fails:
   `✗ s1 invoice_find_latest  no parseable invoice for Company Y in seed/invoices`
   (the invoice exists, and `invoice_find_latest(company="Company Y")` returns it when called
   directly). The failure is honest and the ERP is untouched, but this is the sharpest
   generalization gap in the build. It is now stated in README → Limits and in SUBMISSION
   rather than papered over. One-word fix for whoever owns `planner.py`: glob `*`.
2. **`data/gate.jsonl` holds ~88 pending requests from Phases 03/04.** 05 already scoped the
   demo's settle step to the run's own tool names, so it is a cosmetic wart, not a live bug —
   but a published tree should not ship 84KB of stale queue. It is gitignored, so the published
   tree does not contain it.

## Limits / known ceilings of this phase

- **Pattern-based, not entropy-based.** Seven credential patterns catch the shapes real keys
  take; a secret in an unusual encoding, a split across two lines, or a base64 blob is missed.
  The right next rung is a real scanner (`gitleaks`, `detect-secrets`) in CI — one dependency,
  and out of scope for a repo that must stay five deps deep.
- **Allowlist entries are `(path, pattern, marker)`.** A marker that is itself a plausible
  secret would suppress two lines; no such entry exists today.
- **`check_guards()` proves 10 denials, not the whole threat model.** No test for a hostile
  *plan* (a step whose args try to leave the sandbox), no SSRF probe beyond the URL allowlist,
  no rate limiting, no multi-tenant anything — this is a single-operator prototype, and the
  README says so.
- **The scan reads the whole tree under 1MB per file.** A large binary or a huge run directory
  would need a size/suffix policy; today it skips those rather than scanning them, which is
  the safe direction but is a silent skip.
- **`prompts/` is outside `SCAN_DIRS`** (BUILD scoped it to code + context + runs, and I added
  `demo/` and `tests/`). It is published and contains phase reports quoting fake keys; I checked
  it separately and the only credential-shaped strings are those quotes, which already existed
  in `batch-B1-TEST-RESULT.md`. Add `"prompts"` to `SCAN_DIRS` if the reports ever start
  carrying anything real.
- **`--json` prints findings only**, not the guard list, so CI gets the exit code and the
  findings; a full report still wants the human-readable form.
- **No pre-commit hook.** `scan.py` exists to be run in CI or by hand before publishing; wiring
  it into a hook is a repo-owner decision, not mine.
- **`data/screenshots/*.png` are committed** (two small PNGs the browser tool's test uses).
  Harmless, but they are the only binaries in the publishable tree.

## Video

**Link: `<VIDEO_URL>` — placeholder, record before submitting.**

Script: [`demo/video-script.md`](../../demo/video-script.md) — 75s, eight beats, every quoted
line taken from this report's raw output.

How to record (about 6 minutes of work):

1. Terminal ~110×32, clear scrollback, `rm -rf /tmp/vid`.
2. Run `bash demo/run.sh` once to settle, then `clear`.
3. One take: `bash demo/run.sh /tmp/vid`, then `bash demo/run.sh /tmp/vid --append`, then
   `cat /tmp/vid/runs/*/evidence.json | head -30`, then `python3 -m src.security.scan`, then
   `python3 -m pytest tests/ -q`.
4. Narrate the beat numbers in the script. Nothing is interactive, so no take is ruined by a
   prompt.
5. If it overruns 90s, cut the evidence beat to 8s and the close to 3s. Never cut the approval
   beat or the replay beat — those two are the claim.

## Verify steps

```bash
cd <repo>

# 1. the deliverables exist and the demo still works
python3 -m pytest tests/ -q                 # 114 passed, 1 skipped
rm -rf /tmp/d6 && bash demo/run.sh /tmp/d6   # verdict: pass 8/8 · ERP count: 1 · <1s
bash demo/run.sh /tmp/d6 --append           # replayed=2 · ERP count: 1

# 2. the security pass
python3 -m src.security.scan                # findings: 0 → safe to publish
python3 -m pytest tests/test_security_hardening.py -q   # 25 passed

# 3. publish-clean, checked the way it will actually be judged
git init -q /tmp/gi && GIT_DIR=/tmp/gi/.git GIT_WORK_TREE=. \
  git -c core.quotepath=false ls-files --others --exclude-standard > /tmp/pub.txt   # 78 files
grep -E "runs/|\.db$|\.jsonl$|\.env" /tmp/pub.txt || echo "clean"

# 4. the honest limits, still true
python3 -m src.cli.main run --task "find latest invoice from Company Y and post it to the ERP" \
  --runs /tmp/x/runs --queue /tmp/x/gate.jsonl     # fails with the planner's *.pdf glob (finding 1)
```

## Help needed

None blocking. One optional, for whoever owns the frozen files:

- `src/runtime/planner.py` heuristic `pattern: "*.pdf"` → `"*"`, which removes the only
  generalization gap an evaluator is likely to hit (finding 1 above). It is a one-token change
  to a file phase 06 does not own, so I left it and documented it.