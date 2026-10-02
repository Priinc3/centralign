"""Invoice parsing: PDF/TXT text extraction by regex, then amount+due+company fields.

ponytail: the PDF path reads uncompressed content streams (one `(...) Tj` per line), which
covers the seed corpus and any PDF we generate. For compressed/real-world PDFs swap in
pypdf (`pypdf.PdfReader(...).pages[].extract_text()`) behind pdf_text(). Dates are ISO-only.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from pathlib import Path

from .files_tool import list_files, safe_path

TJ = re.compile(rb"\(((?:[^()\\]|\\.)*)\)\s*Tj")
ESC = re.compile(rb"\\(.)")
ESCAPES = {b"n": b"\n", b"r": b"\r", b"t": b"\t"}

CURRENCIES = ("USD", "EUR", "GBP", "INR")
SYMBOLS = {"$": "USD", "€": "EUR", "£": "GBP", "₹": "INR"}

FIELDS = {
    "invoice_number": re.compile(r"Invoice\s*(?:Number|No\.?|#)\s*[:.]?\s*(\S+)", re.I),
    "issued": re.compile(r"Invoice\s*Date\s*[:.]?\s*(\d{4}-\d{2}-\d{2})", re.I),
    "due": re.compile(r"Due\s*Date\s*[:.]?\s*(\d{4}-\d{2}-\d{2})", re.I),
    "amount": re.compile(
        r"(?:Amount\s*Due|Grand\s*Total|Total\s*Due|Balance\s*Due)\s*[:.]?\s*"
        r"(?:USD|EUR|GBP|INR|\$|€|£|₹)?\s*([\d,]+(?:\.\d{1,2})?)",
        re.I,
    ),
    "currency": re.compile(r"\b(USD|EUR|GBP|INR)\b|([$€£₹])"),
    "company": re.compile(r"company\s*[:=]\s*([^)\n]+)", re.I),
}

MANIFEST = {
    "name": "invoice_parse",
    "description": "Parse one invoice file: vendor, company, invoice number, issued/due dates, amount.",
    "risk": "read",
    "idempotent": True,
    "requires_approval": False,
    "side_effect_free": True,
    "parameters": {
        "type": "object",
        "additionalProperties": False,
        "required": ["path"],
        "properties": {"path": {"type": "string", "description": "Relative to data/"}},
    },
}

FIND_MANIFEST = {
    **MANIFEST,
    "name": "invoice_find_latest",
    "description": "Parse every invoice in a directory and return the latest one for a company.",
    "parameters": {
        "type": "object",
        "additionalProperties": False,
        "required": ["company", "dir", "pattern"],
        "properties": {
            "company": {"type": "string"},
            "dir": {"type": "string", "description": "Directory under data/, default seed/invoices"},
            "pattern": {"type": "string", "description": "Glob, default '*'"},
        },
    },
}


def pdf_text(data: bytes) -> str:
    """One `(...) Tj` per drawn line; undo the PDF string escapes inside each literal."""
    lines = (ESC.sub(lambda m: ESCAPES.get(m.group(1), m.group(1)), m.group(1))
             for m in TJ.finditer(data))
    return "\n".join(line.decode("latin-1") for line in lines)


def text_of(path: Path) -> str:
    raw = path.read_bytes()
    if path.suffix.lower() == ".pdf":
        return pdf_text(raw)
    return raw.decode("utf-8", "replace")


def parse_invoice(path: Path) -> dict:
    text = text_of(path)
    out: dict = {"file": path.name}
    for key, rx in FIELDS.items():
        m = rx.search(text)
        if not m:
            continue
        val = next((g for g in m.groups() if g), m.group(0)).strip()
        out[key] = val
    head = text.splitlines()[0] if text.strip() else ""
    out["vendor"] = re.sub(r"\s*\(.*$", "", head).strip()
    if out.get("company") and out["vendor"].lower().startswith(out["company"].lower()):
        out["vendor"] = out["company"]
    if "amount" in out:
        try:
            out["amount"] = str(Decimal(out["amount"].replace(",", "")).quantize(Decimal("0.01")))
        except InvalidOperation:
            out["parse_error"] = f"unreadable amount: {out['amount']!r}"
    sym = out.pop("currency", None)
    out["currency"] = sym if sym in CURRENCIES else SYMBOLS.get(sym, "USD")
    out["ok"] = "amount" in out and "due" in out
    return out


def find_latest(company: str, directory: str = "seed/invoices", pattern: str = "*") -> dict:
    found = list_files(directory, pattern)
    parsed = []
    for f in found["files"]:
        try:
            rec = parse_invoice(safe_path(f["path"]))
        except (OSError, ValueError) as e:
            parsed.append({"file": f["name"], "ok": False, "parse_error": str(e)})
            continue
        parsed.append(rec)
    matches = [r for r in parsed if r.get("ok") and company.lower() in (r.get("company") or "").lower()]
    matches.sort(key=lambda r: (r.get("issued", ""), r.get("invoice_number", "")), reverse=True)
    return {
        "ok": bool(matches),
        "company": company,
        "scanned": found["count"],
        "candidates": parsed,
        "matched": len(matches),
        "latest": matches[0] if matches else None,
        "error": None if matches else f"no parseable invoice for {company} in {directory}",
    }


def run(args: dict) -> dict:
    rec = parse_invoice(safe_path(args["path"]))
    if rec["ok"]:
        return rec
    return {"ok": False, **rec, "error": rec.get("parse_error", "missing amount or due date")}


def run_find_latest(args: dict) -> dict:
    # strict mode sends "" for optional args, so `or` (not .get's default) restores real defaults.
    return find_latest(args["company"], args.get("dir") or "seed/invoices",
                       args.get("pattern") or "*")
