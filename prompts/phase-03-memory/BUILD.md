# BUILD — Phase 03 memory + policy (G1)

You are Phase 03 (G1). Siblings running now: [01-runtime: src/runtime/*, src/ledger/*, src/contracts/*], [02-tools: src/tools/*, sim_app/*]. Your OWN files: `src/memory/*`, `src/policy/*`, `context/*`. DO NOT TOUCH: 01/02 OWN files. Shared read-only: `src/contracts/` (Memory API shape, risk tiers). Comm folder: `prompts/parallel-G1/`.

## Context + end goal
See `prompts/00-plan.md`. You make it a company employee: remembers, obeys policies, asks approval on risk.

## Goal
Persistent company memory + versioned YAML policies + risk-tiered approval gate.

## Deliverables (OWN files only)
- `src/memory/store.py` (SQLite WAL, companies/facts/runs tables, single-writer), `recall.py` (top-k facts for task).
- `src/policy/loader.py` (YAML load+validate), `gate.py` (`allow|approve|deny` per tool+risk, logs decision).
- `context/company.yaml` (Company X: sources, ERP endpoint, approval threshold), `context/policies.yaml` (allowlist domains, max amount auto-post, PII redact list), `context/tools.yaml` (optional registry mirror).
- `tests/test_memory_policy.py` (recall returns seeded fact; gate denies evil domain, requires approval over threshold).

## Criteria (must run)
- `python -m pytest tests/test_memory_policy.py -q` passes.
- `python -m src.policy.gate --tool erp.post --amount 999999` → `approve`; `--amount 10` → `allow`; `--domain evil.com` → `deny`.
- WAL pragmas set; no secrets in YAML (placeholders only).

## Constraints (verified)
- SQLite WAL + busy_timeout, single writer: https://www.sqlite.org/wal.html
- YAML policies versioned (`version: 1`, `updated:` date); PII redact before memory write.
- Quality: versioned context, deterministic gate (no LLM in gate). Fast: indexed recall, <50ms gate. Secure: deny-by-default, approval queue file-based.

## Parallel rules
COMM.md `## 03 HH:MM — <25 words` + tag; STATUS.md ONLY your row. Check COMM+STATUS at start + before REPORT. Contract mismatch → HELP, don't edit `src/contracts/`.
Stub if creating: add row `| 03 | ACTIVE | <time> | memory+policy | — |`.

## Order
Write `prompts/phase-03-memory/REPORT.md` with files changed, cmds+raw output, verify steps, limits, help needed.
