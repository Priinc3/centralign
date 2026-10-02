"""Phase 02 smoke: files + invoice parse + allowlist + ERP roundtrip. No LLM, no network
beyond the in-process sim ERP, no Playwright install required."""

from __future__ import annotations

import json
import pathlib
import sys
import threading
from decimal import Decimal

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from sim_app.server import make_server  # noqa: E402
from src.contracts.tools import ToolManifest  # noqa: E402
from src.tools import browser_tool, execute, files_tool, invoice_tool, manifest_registry  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
EXPECTED = json.loads((ROOT / "data" / "seed" / "expected.json").read_text())


def args(tool: str, **given):
    """Strict mode wants every property present and typed; defaults() fills the rest."""
    return {**manifest_registry.defaults(tool), **given}


# --- files -----------------------------------------------------------------
def test_files_list_seeds_inside_sandbox():
    out = files_tool.list_files("seed/invoices")
    assert out["count"] == len(EXPECTED["candidates"]) == 3


@pytest.mark.parametrize("evil", ["/etc/passwd", "../../../etc/passwd", "~/secrets", ".."])
def test_files_sandbox_rejects_escapes(evil):
    with pytest.raises(ValueError):
        files_tool.safe_path(evil)


def test_files_read_returns_bytes_and_text():
    out = files_tool.read_file("seed/invoices/INV-X-2024-0912-acme.pdf")
    assert out["bytes"] > 500 and out["content"].startswith("%PDF-1.4")


def test_files_read_refuses_to_escape_sandbox_via_registry():
    out = execute("files_read", args("files_read", path="../../etc/passwd"))
    assert out["ok"] is False and "escapes data/ sandbox" in out["error"]


# --- invoice parsing -------------------------------------------------------
def test_find_latest_picks_correct_company_and_date():
    out = invoice_tool.find_latest(EXPECTED["company"])
    assert out["ok"] and out["matched"] == 2, out["candidates"]
    assert out["latest"]["file"] == EXPECTED["latest"]["file"]


def test_parse_matches_expected_json_exactly():
    got = invoice_tool.parse_invoice(files_tool.safe_path("seed/invoices/" + EXPECTED["latest"]["file"]))
    want = EXPECTED["latest"]
    assert Decimal(got["amount"]) == Decimal(want["amount"]), "amount must be exact (no float drift)"
    for key in ("invoice_number", "issued", "due", "currency", "vendor", "company"):
        assert got[key] == want[key], f"{key}: {got[key]!r} != {want[key]!r}"


def test_pdf_text_matches_a_real_pdf_reader():
    """Guard the regex extractor against poppler when it is installed."""
    import shutil
    import subprocess

    pdf = ROOT / "data" / "seed" / "invoices" / EXPECTED["latest"]["file"]
    mine = invoice_tool.pdf_text(pdf.read_bytes())
    for line in ("Invoice Number: CX-2024-0912", "Due Date: 2024-10-12", "Amount Due: USD 4,820.00"):
        assert line in mine, line
    if shutil.which("pdftotext"):
        theirs = subprocess.run(["pdftotext", "-layout", str(pdf), "-"],
                                capture_output=True, text=True, check=True).stdout
        assert "Amount Due: USD 4,820.00" in theirs, "seed PDF is not valid text for poppler"


# --- browser allowlist (no Playwright needed) ------------------------------
def test_allowlist_blocks_evil_com(monkeypatch):
    monkeypatch.setenv("ALLOWLIST", "localhost,example.com")
    assert browser_tool.check_url("http://localhost:8901/portal").startswith("http")
    assert browser_tool.check_url("https://example.com/invoices").startswith("https")
    for bad in ("http://evil.com", "https://evil.com/x", "http://example.com.evil.com",
                "https://sub.evil.com/", "file:///etc/passwd", "javascript:alert(1)"):
        with pytest.raises(browser_tool.UrlNotAllowed):
            browser_tool.check_url(bad)


def test_registry_blocks_evil_com_without_launching_browser(monkeypatch):
    monkeypatch.setenv("ALLOWLIST", "localhost,example.com")

    def boom():
        raise AssertionError("Playwright must never be reached for a blocked URL")

    monkeypatch.setattr(browser_tool, "_context", boom)
    out = execute("browser_open", args("browser_open", url="http://evil.com"))
    assert out["ok"] is False and out["blocked_by"] == "allowlist" and out["tool"] == "browser_open"


# --- registry contract -----------------------------------------------------
def test_every_manifest_validates_against_the_frozen_contract():
    reg = manifest_registry.registry()
    assert set(reg) == set(manifest_registry.TOOLS)
    for name, man in reg.items():
        assert isinstance(man, ToolManifest)
        assert man.risk in ("read", "write", "destructive")
        assert man.openai_tool()["function"]["strict"] is True
    assert {n for n, m in reg.items() if m.risk == "write"} == {"erp_post_invoice"}


def test_registry_accepts_dotted_policy_ids():
    """Phase 03's gate/policies key on dotted ids; contract NAME_RE forbids dots."""
    for dotted, legal in (("erp.post", "erp_post_invoice"), ("invoice.parse", "invoice_parse"),
                          ("browser.fetch", "browser_open"), ("files.list", "files_list")):
        assert manifest_registry.resolve(dotted) == legal


def test_callables_take_kwargs_like_the_executor_expects():
    fns = manifest_registry.callables()
    assert set(fns) == set(manifest_registry.TOOLS)
    out = fns["files_list"](**args("files_list", dir="seed/invoices"))
    assert out["ok"] and out["count"] == 3


def test_registry_rejects_bad_args():
    out = execute("invoice_parse", args("invoice_parse", surprise=1))
    assert out["ok"] is False and "unexpected arg 'surprise'" in out["error"]
    assert execute("invoice_parse", {})["ok"] is False
    out = execute("invoice_parse", {"path": 7})
    assert out["ok"] is False and "must be string" in out["error"]
    assert execute("nope_tool", {})["ok"] is False


def test_destructive_tools_require_confirmation(monkeypatch):
    entry = ("src.tools.files_tool", "MANIFEST", "run")
    monkeypatch.setitem(manifest_registry.TOOLS, "files_purge", entry)
    monkeypatch.setitem(files_tool.MANIFEST, "risk", "destructive")
    monkeypatch.setitem(files_tool.MANIFEST, "name", "files_purge")
    args = {"path": "x", "max_bytes": 100}
    blocked = execute("files_purge", args)
    assert blocked["status"] == "confirm_required" and blocked["risk"] == "destructive"
    confirmed = execute("files_purge", args, confirmed=True)
    assert "status" not in confirmed, "confirm_required gate must be passed, then the tool really runs"


# --- ERP roundtrip ---------------------------------------------------------
@pytest.fixture()
def erp(tmp_path):
    """In-process sim ERP on an ephemeral port + temp DB."""
    srv = make_server("127.0.0.1", 0, tmp_path / "erp.db")
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()
    srv.server_close()


def test_erp_post_is_idempotent_double_post_one_row(erp):
    invoice = invoice_tool.parse_invoice(
        files_tool.safe_path("seed/invoices/" + EXPECTED["latest"]["file"]))
    body = args("erp_post_invoice", base_url=erp,
                vendor=invoice["vendor"], company=invoice["company"],
                invoice_number=invoice["invoice_number"], amount=invoice["amount"],
                currency=invoice["currency"], due_date=invoice["due"], source_file=invoice["file"])

    first = execute("erp_post_invoice", body)
    second = execute("erp_post_invoice", body)
    assert first["ok"] and first["status"] == 201 and first["body"]["created"] is True
    assert second["ok"] and second["status"] == 200 and second["body"]["created"] is False
    assert first["body"]["id"] == second["body"]["id"], "idempotency-key must reuse the row"
    assert first["idempotency_key"] == second["idempotency_key"]
    assert Decimal(first["body"]["amount"]) == Decimal(EXPECTED["latest"]["amount"])

    listed = execute("erp_post_invoice", args("erp_post_invoice", action="list", base_url=erp))
    assert listed["ok"] and listed["body"]["count"] == 1, "double POST must leave exactly 1 row"
    # regression: company names contain spaces, so the filter has to be URL-encoded
    filtered = execute("erp_post_invoice", args("erp_post_invoice", action="list",
                                                 company="Company X", base_url=erp))
    assert filtered["ok"], filtered.get("error")
    assert filtered["body"]["count"] == 1 and filtered["body"]["invoices"][0]["id"] == first["body"]["id"]
    missing = execute("erp_post_invoice", args("erp_post_invoice", action="list",
                                               company="No Such Co", base_url=erp))
    assert missing["ok"] and missing["body"]["count"] == 0


def test_erp_rejects_missing_fields_and_bad_amount(erp):
    bad = execute("erp_post_invoice", args("erp_post_invoice", vendor="A", company="B",
                                            amount="abc", base_url=erp))
    assert bad["ok"] is False and bad["status"] == 422
    empty = execute("erp_post_invoice", args("erp_post_invoice", base_url=erp))
    assert empty["ok"] is False and empty["status"] == 422


def test_erp_idempotency_key_is_content_derived():
    from src.tools import erp_tool

    assert erp_tool.idempotency_key({"a": 1, "b": 2}) == erp_tool.idempotency_key({"b": 2, "a": 1})
    assert erp_tool.idempotency_key({"a": 1}) != erp_tool.idempotency_key({"a": 2})


def test_erp_unreachable_is_an_error_not_a_crash():
    from src.tools import erp_tool

    res = erp_tool.list_invoices(base="http://127.0.0.1:1")
    assert res["ok"] is False and "unreachable" in res["error"]


# --- live browser (skipped unless playwright is installed) -----------------
def test_browser_opens_allowlisted_localhost_page(erp):
    pytest.importorskip("playwright", reason="playwright not installed; allowlist tests above still run")
    out = execute("browser_open", args(
        "browser_open", url=f"{erp}/portal", wait_for="#invoices", text="#invoices",
        screenshot="screenshots/test-portal.png"))
    assert out["ok"] and out["status"] == 200 and out["title"] == "Invoice portal", out.get("error")
    assert EXPECTED["latest"]["file"] in out["text"], "browser must see the seeded invoices"
    shot = ROOT / "data" / out["screenshot"].split("data/")[-1]
    assert shot.exists() and shot.stat().st_size > 1000, "screenshot must land in the data/ sandbox"
    browser_tool.close()


# --- end to end: find latest -> post ---------------------------------------
def test_find_latest_then_post_offline(erp, monkeypatch):
    monkeypatch.setenv("ERP_URL", erp)
    found = execute("invoice_find_latest", args("invoice_find_latest", company="Company X"))
    assert found["ok"] and found["latest"]["file"] == EXPECTED["latest"]["file"]
    inv = found["latest"]
    posted = execute("erp_post_invoice", args(
        "erp_post_invoice", vendor=inv["vendor"], company=inv["company"],
        invoice_number=inv["invoice_number"], amount=inv["amount"], currency=inv["currency"],
        due_date=inv["due"], source_file=inv["file"]))
    assert posted["ok"] and Decimal(posted["body"]["amount"]) == Decimal(EXPECTED["latest"]["amount"])
