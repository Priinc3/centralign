"""Phase 06 hardening: allowlist, traversal, redaction, and the pre-publish scan.

Five security claims an evaluator can re-run:
  1. evil.com is denied, including the example.com.evil.com suffix trick
  2. ../../etc/passwd comes back as a failed envelope with no file content in it
  3. the redactor still fires on a live secret (a "no leak" claim needs a positive control)
  4. nothing in the tree looks like a credential, and the scan catches a planted one
  5. an undeclared tool is denied, not defaulted to allow
"""

from __future__ import annotations

import json
import pathlib
import sys
import time

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from src.contracts.events import redact  # noqa: E402
from src.policy.gate import UNKNOWN_TOOL, decide  # noqa: E402
from src.security import scan  # noqa: E402
from src.tools import browser_tool, execute, files_tool, manifest_registry  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]


def args(tool: str, **given):
    return {**manifest_registry.defaults(tool), **given}


# --- 1. allowlist ---------------------------------------------------------
@pytest.mark.parametrize(
    "url",
    ["http://evil.com/", "http://example.com.evil.com/", "https://evil.com/example.com",
     "http://notexample.com/", "file:///etc/passwd", "javascript:alert(1)"],
)
def test_browser_denies_every_non_allowlisted_url(url):
    with pytest.raises(browser_tool.UrlNotAllowed):
        browser_tool.check_url(url)


@pytest.mark.parametrize("host", ["evil.com", "example.com.evil.com", "notexample.com", "EVIL.COM"])
def test_gate_denies_domain_outside_allowlist(host):
    assert decide(tool="browser.fetch", domain=host, log=False).verdict == "deny"


def test_gate_allows_the_allowlisted_host():
    assert decide(tool="browser.fetch", domain="example.com", log=False).verdict == "allow"


# --- 2. path traversal, through the real dispatch -------------------------
@pytest.mark.parametrize("evil", ["../../etc/passwd", "../../../etc/passwd", "/etc/passwd", "~/x"])
def test_files_read_traversal_returns_envelope_without_content(evil):
    envelope = execute("files_read", args("files_read", path=evil))
    assert envelope["ok"] is False
    assert "root:" not in json.dumps(envelope)  # nothing from the real /etc/passwd
    assert "sandbox" in envelope["error"] or "relative to data/" in envelope["error"]
    assert "content" not in envelope


def test_traversal_error_is_redacted_before_it_hits_the_ledger():
    envelope = execute("files_read", args("files_read", path="../../etc/passwd"))
    event = redact({"payload": envelope})
    assert "content" not in event["payload"]


# --- 3. redaction positive control ----------------------------------------
def test_redactor_fires_on_a_live_secret():
    probe = {"api_key": "sk-" + "A" * 24, "Authorization": "Bearer " + "b" * 20,
             "note": "key sk-" + "C" * 30 + " used", "password": "hunter2hunter2"}
    clean = json.dumps(redact(probe))
    assert "sk-" not in clean and "Bearer b" not in clean
    assert clean.count("[REDACTED]") == 4


# --- 4. nothing in the tree looks like a credential ------------------------
def test_repo_is_clean_of_secrets():
    findings, suppressed = scan.check_secrets()
    assert findings == [], [str(f) for f in findings]
    assert suppressed == len(scan.ALLOWLIST) > 0  # deliberate canaries, marker-checked


def test_scan_catches_a_planted_secret(tmp_path, monkeypatch):
    planted = tmp_path / "src"
    planted.mkdir()
    # Joined at runtime so this line does not match the scanner scanning itself.
    (planted / "leak.py").write_text('KEY = "sk-proj-' + "AAAA" * 6 + '"\n')
    monkeypatch.setattr(scan, "ROOT", tmp_path)
    monkeypatch.setattr(scan, "SCAN_DIRS", ("src",))
    findings, _ = scan.check_secrets()
    assert [f.where for f in findings] == ["src/leak.py:1"]


def test_allowlist_entry_only_covers_its_own_marker(tmp_path, monkeypatch):
    planted = tmp_path / "src"
    planted.mkdir()
    (planted / "leak.py").write_text('KEY = "sk-' + "A" * 24 + '"\n')
    monkeypatch.setattr(scan, "ROOT", tmp_path)
    monkeypatch.setattr(scan, "SCAN_DIRS", ("src",))
    monkeypatch.setattr(scan, "ALLOWLIST", (("src/leak.py", "openai_key", "CANARY-MARKER"),))
    findings, _ = scan.check_secrets()
    assert [f.where for f in findings] == ["src/leak.py:1"]


def test_no_env_file_and_gitignore_covers_one():
    assert scan.check_env() == []
    assert not list(ROOT.rglob(".env"))


def test_full_scan_is_fast_and_green():
    start = time.monotonic()
    assert scan.main([]) == 0
    assert time.monotonic() - start < 5.0


# --- 5. deny by default ---------------------------------------------------
def test_gate_denies_undeclared_tool():
    decision = decide(tool=UNKNOWN_TOOL, log=False)
    assert decision.verdict == "deny"
    assert "not in context/tools.yaml registry" in decision.reason


def test_gate_denies_over_ceiling_even_for_a_known_tool():
    assert decide(tool="erp.post", amount=10**9, log=False).verdict == "deny"


def test_guard_self_tests_are_all_green():
    assert scan.check_guards() == []
