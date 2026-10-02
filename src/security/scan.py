"""Pre-publish scan: credentials in the tree, .env discipline, guard self-tests.

    python3 -m src.security.scan            # 0 findings + "clean" == safe to publish, rc=0
    python3 -m src.security.scan --json     # same findings as JSON, for CI

Four checks, stdlib only, <5s:

  1. no credential-shaped strings under src/ context/ sim_app/ demo/ tests/ runs/
  2. every suppressed line is an allowlisted deliberate canary (marker must be present)
  3. no .env in the tree, and .gitignore covers one
  4. the frozen guards still deny: unknown tool, evil host, path traversal, secret key

Check 4 imports the real modules and calls the real chokepoints, so a refactor that
loosens gate/browser/files cannot pass CI silently.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCAN_DIRS = ("src", "context", "sim_app", "demo", "tests", "runs")
SKIP_DIRS = {"__pycache__", ".pytest_cache", ".git", "node_modules"}
MAX_BYTES = 1_000_000
TEXT_SUFFIXES = {".py", ".md", ".yaml", ".yml", ".json", ".jsonl", ".txt", ".sh", ".sql", ".toml", ".cfg", ".env", ""}

PATTERNS: dict[str, re.Pattern[str]] = {
    # sk- followed by real key entropy: the redactor's own literal (sk-[A-Za-z...]) cannot match.
    "openai_key": re.compile(r"\bsk-[A-Za-z0-9_-]{20,}"),
    "bearer_token": re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/-]{12,}=*"),
    "assigned_secret": re.compile(
        r"""(?i)\b(?:password|passwd|secret|api[_-]?key|access[_-]?token|auth[_-]?token|client[_-]?secret)"""
        r"""\s*[:=]\s*["'][^"'\s]{8,}["']"""
    ),
    "private_key": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "aws_key": re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    "slack_token": re.compile(r"\bxox[abposr]-[A-Za-z0-9-]{10,}"),
    "github_token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}"),
}

# Deliberate test canaries, allowed only while the line still carries its marker.
# (path prefix, pattern, marker) — drop the marker from the line and it is a finding again.
ALLOWLIST: tuple[tuple[str, str, str], ...] = (
    ("tests/test_runtime_smoke.py", "openai_key", "DO-NOT-LOG"),
    ("tests/test_reliability_offline.py", "openai_key", "SECRET-1234"),
)


class Finding:
    __slots__ = ("check", "where", "message")

    def __init__(self, check: str, where: str, message: str) -> None:
        self.check, self.where, self.message = check, where, message

    def as_dict(self) -> dict[str, str]:
        return {"check": self.check, "where": self.where, "message": self.message}

    def __str__(self) -> str:
        return f"{self.check:8} {self.where}: {self.message}"


def _files() -> list[Path]:
    out: list[Path] = []
    for rel in SCAN_DIRS:
        base = ROOT / rel
        if not base.exists():
            continue
        for p in base.rglob("*"):
            if not p.is_file() or SKIP_DIRS & set(p.parts):
                continue
            if p.suffix.lower() not in TEXT_SUFFIXES:
                continue
            try:
                if p.stat().st_size <= MAX_BYTES:
                    out.append(p)
            except OSError:
                continue
    for extra in ("README.md", "SUBMISSION.md", "requirements.txt", ".gitignore"):
        p = ROOT / extra
        if p.is_file():
            out.append(p)
    return sorted(out)


def check_secrets() -> tuple[list[Finding], int]:
    findings, suppressed = [], 0
    for path in _files():
        rel = str(path.relative_to(ROOT))
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            findings.append(Finding("read", rel, str(exc)))
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            for name, rx in PATTERNS.items():
                if not rx.search(line):
                    continue
                allowed = next(
                    (a for a in ALLOWLIST if rel.startswith(a[0]) and a[1] == name and a[2] in line), None
                )
                if allowed:
                    suppressed += 1
                    continue
                findings.append(Finding("secret", f"{rel}:{lineno}", f"{name}: {line.strip()[:70]}"))
    return findings, suppressed


def check_env() -> list[Finding]:
    findings: list[Finding] = []
    leaked = sorted(str(p.relative_to(ROOT)) for p in ROOT.rglob(".env*") if SKIP_DIRS & set(p.parts))
    findings += [Finding("env", name, "credential file in the tree, must never be committed") for name in leaked]
    ignore = (ROOT / ".gitignore").read_text(encoding="utf-8") if (ROOT / ".gitignore").is_file() else ""
    for pattern in (".env", "runs/", "*.db", "*.jsonl"):
        if not any(ln.strip() in (pattern, pattern + "*") for ln in ignore.splitlines()):
            findings.append(Finding("env", ".gitignore", f"does not ignore {pattern}"))
    return findings


def check_guards() -> list[Finding]:
    """Call the real guards; a guard that stopped denying is a finding."""
    sys.path.insert(0, str(ROOT))
    from src.contracts.events import redact
    from src.policy.gate import UNKNOWN_TOOL, decide
    from src.tools import browser_tool, files_tool

    out: list[Finding] = []

    def denied(label: str, fn, *a, **kw) -> None:
        """A guard denies either by raising (browser/files) or by verdict (gate)."""
        try:
            got = fn(*a, **kw)
        except Exception:
            return
        verdict = getattr(got, "verdict", "returned")
        if verdict != "deny":
            out.append(Finding("guard", label, f"verdict={verdict!r}, expected deny"))

    denied("gate/unknown-tool", decide, tool=UNKNOWN_TOOL, log=False)
    denied("gate/evil-domain", decide, tool="browser.fetch", domain="evil.com", log=False)
    denied("gate/allowlist-suffix", decide, tool="browser.fetch", domain="example.com.evil.com", log=False)
    denied("gate/over-ceiling", decide, tool="erp.post", amount=10**9, log=False)
    denied("browser/evil-host", browser_tool.check_url, "http://evil.com/")
    denied("browser/suffix-trick", browser_tool.check_url, "http://example.com.evil.com/")
    denied("browser/file-scheme", browser_tool.check_url, "file:///etc/passwd")
    denied("files/traversal", files_tool.safe_path, "../../etc/passwd")
    denied("files/absolute", files_tool.safe_path, "/etc/passwd")
    denied("files/nul-byte", files_tool.safe_path, "seed/\x00x")

    # Positive control: a scanner that finds nothing because it matches nothing is worthless.
    # The pieces are joined at runtime so this line does not match this file's own patterns.
    probe = {"api_key": "sk-" + "A" * 24, "Authorization": "Bearer " + "b" * 20}
    if redact(probe) == probe or "sk-" in json.dumps(redact(probe)):
        out.append(Finding("guard", "redact", "redactor no longer masks a secret-looking payload"))
    return out


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    secrets, suppressed = check_secrets()
    findings = secrets + check_env() + check_guards()

    if "--json" in argv:
        print(json.dumps({"findings": [f.as_dict() for f in findings], "allowlisted": suppressed}, indent=2))
        return 1 if findings else 0

    print(f"scanning {len(SCAN_DIRS)} trees for credentials  … {len(findings) and 'see below' or 'none'}")
    for finding in findings:
        print(f"  ✗ {finding}")
    if suppressed:
        print(f"allowlisted canaries  {suppressed}  (tests/, marker-checked: the line must still say why)")
    print(
        "guards  deny unknown tool · deny evil host + suffix trick · deny /etc traversal · "
        "redactor masks a live secret"
    )
    print(f"\nfindings: {len(findings)}" + ("  → NOT safe to publish" if findings else "  → safe to publish"))
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
