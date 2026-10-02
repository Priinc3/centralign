import json
import shutil

import pytest

from src.memory.recall import recall
from src.memory.store import Store
from src.policy.gate import decide, main
from src.policy.loader import CONTEXT_DIR, PolicyError, load_context


@pytest.fixture
def store(tmp_path):
    with Store(tmp_path / "memory.db") as s:
        s.add_company("company_x", "Company X")
        yield s


def test_wal_pragmas_on(store):
    assert store.pragma("journal_mode") == "wal"
    assert store.pragma("busy_timeout") == 5000


def test_recall_returns_seeded_fact(store):
    store.remember("company_x", "vendor", "acme_payment_terms", "net 30 from invoice date", "portal")
    store.remember("company_x", "vendor", "acme_address", "somewhere else entirely", "portal")
    hits = recall(store, "company_x", "what are the acme payment terms?", k=1)
    assert hits and hits[0]["key"] == "acme_payment_terms"
    assert "net 30" in hits[0]["value"]


def test_recall_empty_query_falls_back_to_recent(store):
    store.remember("company_x", "vendor", "k", "v")
    assert len(recall(store, "company_x", "  ???  ")) == 1


def test_pii_redacted_before_write(store):
    store.remember("company_x", "vendor", "acme_contact", "ap@acme.com 555-123-4567")
    stored = store.facts("company_x")[0]
    assert "ap@acme.com" not in stored["value"]
    assert "[REDACTED:email]" in stored["value"]
    assert stored["redacted"] == 1


def test_gate_denies_evil_domain():
    assert decide("browser.fetch", domain="evil.com").verdict == "deny"
    assert decide("erp.post", amount=1, domain="evil.com").verdict == "deny"
    assert decide("browser.fetch", domain="example.com").verdict == "allow"


def test_gate_threshold_allows_small_post_and_asks_for_big_one():
    assert decide("erp.post", amount=10).verdict == "allow"
    big = decide("erp.post", amount=999999)
    assert big.verdict == "approve"
    assert big.request_id
    assert decide("erp.post", amount=1000000.01).verdict == "deny"


def test_gate_denies_unknown_tool_and_underspecified_post():
    assert decide("erp.delete_everything", amount=1).verdict == "deny"
    assert decide("erp.post").verdict == "approve"  # no amount yet -> human confirms


def test_gate_logs_every_decision_to_the_queue(tmp_path):
    ctx = load_context()
    ctx["company"]["approval"]["queue"] = str(tmp_path / "gate.jsonl")
    decide("erp.post", amount=999999, context=ctx)
    decide("erp.post", amount=10, context=ctx)
    records = [json.loads(line) for line in (tmp_path / "gate.jsonl").read_text().splitlines()]
    assert [r["verdict"] for r in records] == ["approve", "allow"]
    assert records[0]["queue"] == "pending"


def test_gate_cli_prints_verdict(capsys):
    # appends to the real data/gate.jsonl audit file, same as a live run
    assert main(["--tool", "erp.post", "--amount", "999999"]) == 0
    assert capsys.readouterr().out.strip() == "approve"
    assert main(["--domain", "evil.com"]) == 2
    assert capsys.readouterr().out.strip() == "deny"


def test_loader_rejects_risk_tier_outside_the_frozen_contract(tmp_path):
    for name in ("company.yaml", "policies.yaml", "tools.yaml"):
        shutil.copy(CONTEXT_DIR / name, tmp_path / name)
    tools = tmp_path / "tools.yaml"
    tools.write_text(tools.read_text().replace("risk: read", "risk: low"))
    with pytest.raises(PolicyError, match="RISK_TIERS"):
        load_context(tmp_path)


def test_loader_rejects_missing_context_dir(tmp_path):
    with pytest.raises(PolicyError, match="missing context file"):
        load_context(tmp_path)