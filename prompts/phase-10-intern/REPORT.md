# REPORT — phase-10-intern

Type NORMAL, no siblings. Owner decision applied: **applying as AI Engineering Intern**. The demo
presents intern scope (one invoice flow, genuinely autonomous); the Founding breadth is the
closing beat, not the headline.

Docs-only, per the BUILD exception. Three files touched, all markdown:

| file | change |
|---|---|
| `SUBMISSION.md` | +1 role line (top of packet) |
| `demo/video-script.md` | close beat rewritten 5s → 10s; three timing lines re-balanced to 80s |
| `prompts/phase-08-submission/USER-STEPS.md` | form-field role tick + role-specific-question guidance |

Nothing else was opened for write. No engine file, no test file, no doc number, no `context/*.yaml`,
no prompt `REPORT.md`, not `docs/USER-TEST.md`.

---

## 1. `SUBMISSION.md` — role line (line 3)

Inserted directly under the H1, above the one-line, so it is the second thing read:

```
# SUBMISSION — CentrAlign AI operator

Role: AI Engineering Intern (prototype also demonstrates Founding-scope architecture — see video close)

**One-line:** an AI employee that turns *"find the latest invoice from Company X and post it to
```

Deliberately verbatim from the BUILD so the evaluator's first read is Intern, with the founding
claim as a subordinate clause that points at the video close.

**The criterion-mapping table (lines 27–36) is untouched** — the eight evaluation criteria are
shared by both roles in the posting (*"For both roles, submissions will primarily be evaluated
on…"*), so re-labelling them for the Intern track would have been wrong. Same reason the narrow-genuine
statement, the LLM-evidence section and the honest-limits section are untouched: they are claims
about the system, not about the role.

## 2. `demo/video-script.md` — the close, now 10s

Was:

```
### 1:15 — close (5s)

> Invoice intake, one company profile, done for real: planned, executed, gated by a human,
> verified from the ledger, and evidenced. That's CentrAlign — README has the architecture, the
> limits, and what's next.
```

Now:

```
### 1:15 — close (10s)

> Invoice intake, one company profile, done for real: planned, executed, gated by a human, verified
> from the ledger, and evidenced. That's CentrAlign.
>
> I built this as my **Intern** submission — a narrow invoice flow that genuinely runs. The same
> runtime also carries the **Founding**-scope pieces: frozen contracts, the append-only ledger, the
> independent verifier, the multi-key router — happy to go deep on any of those live.
>
> README has the architecture, the limits, and what's next.
```

The original close survives as the first paragraph, so nothing truthful was lost to make room for
the new beat.

**Truthfulness of the four named pieces — checked in the tree, not asserted:**

| named on camera | source | test coverage |
|---|---|---|
| frozen contracts | `src/contracts/{events,tools,verdict}.py` | `tests/test_runtime_smoke.py`, `tests/test_tools_smoke.py`, `tests/test_security_hardening.py` |
| append-only ledger | `src/ledger/` | `tests/test_runtime_smoke.py`, `tests/test_reliability_offline.py` |
| independent verifier | `src/verifier/` | `tests/test_reliability_offline.py` |
| multi-key router | `src/llm/router.py` | `tests/test_llm_router_keys.py` (offline-pinned) |

Every one of the four has a test file. Nothing was named on camera that isn't there.

### Timing rebalance

Adding 5s to the close moves 75 → 80. Three lines that hard-coded the old figure were updated so
the document doesn't contradict itself: the H1 (`75 seconds` → `80 seconds`), the
`**Total ≈ 75s.**` line, and `**Timing.** The commands take ~1s total; the 75s is narration`. The
"if you run long" guidance changed from *cut the close to 3s* to *cut evidence to 8s* only — the
close is now load-bearing for the positioning, so it is the other one protected. 80s stays inside
the 75–90s window the posting allows and that `RECORDING.md` states.

The `RECORDING.md` block, the keystroke table, and the verified transcript (lines 128–182) are
untouched — the transcript is real captured output and re-recording the close does not invalidate a
single line of it.

## 3. `USER-STEPS.md` — the form role tick

The BUILD said to note it if the file needed the word; it did, so it got it (BUILD explicitly
allows editing USER-STEPS). New first row of the step-3 table:

```
| **Role applied for** | **`AI Engineering Intern`** — tick this one. The packet is framed as the Intern submission (`SUBMISSION.md` line 3); the Founding Engineer role exists at the same company, but the prototype and this submission are the Intern scope. Only switch it if you change your mind about which role you are applying for. |
```

Plus one sentence appended to the "what would you build next" paragraph, so a role-specific form
question is answered from the Intern discussion emphasis (engineering ability, speed of learning,
experimentation, technical understanding) and not from the Founding track's emphasis (architecture,
scalability, security, extensibility).

Neither is padding: the posting has two role boxes on one form, and the whole failure this phase
guards against is the wrong one being ticked.

---

## Verify

```console
$ grep -in "founding" SUBMISSION.md demo/video-script.md
SUBMISSION.md:3:Role: AI Engineering Intern (prototype also demonstrates Founding-scope architecture — see video close)
demo/video-script.md:116:> runtime also carries the **Founding**-scope pieces: frozen contracts, the append-only ledger, the
```

Both hits name Intern first and Founding second — in `SUBMISSION.md:3` Intern is the role and
Founding is a subordinate clause; in `video-script.md` "Intern" is at line 115, one line above the
"Founding" mention at line 116, so the sentence order is intern-then-founding as well as the
byte order.

```console
$ python3 -m src.security.scan
findings: 0  → safe to publish
```

```console
$ python3 -m pytest tests/ -q
133 passed, 1 skipped in 11.35s
```

## One thing this phase found but did not fix

**The suite is 133, the docs say 127.** `SUBMISSION.md` (lines 11, 44, 68) and
`demo/video-script.md` (lines 102, 181, 211) all print `127 passed`. The real number today is
`133 passed, 1 skipped`. This is pre-existing drift from a later phase's tests — nothing in this
phase changed a test — and the BUILD's criteria for this phase are *no engine/test/doc-number
churn*, so the numbers were left exactly as they were.

It is still a live truthfulness risk: the video script tells the camera operator to run
`python3 -m pytest tests/ -q` and expects the output to read `127 passed, 1 skipped in 7.36s`, and
an evaluator running the same command gets `133`. The close beat is the only place this phase
changed narration, and it is unaffected.

**Fix it in one pass before recording:** `grep -rn "127" SUBMISSION.md demo/video-script.md README.md`
→ replace with `133`, drop the pinned `7.36s` (it is a per-machine wall-clock and was already
flagged as such), and re-time the pytest line on the take. Worth its own phase rather than being
folded in here, because a doc-number sweep across the tree is exactly the churn this BUILD forbids.

---

skipped: a role-consistency pass over `README.md`, `docs/USER-TEST.md` and the per-phase REPORTs —
out of scope this phase (read-only), and those files describe the build, not the application. Add
when the role is final and the recording is done.
