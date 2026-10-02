"""Sim ERP client: stdlib urllib, deterministic Idempotency-Key so retries never double-post."""

from __future__ import annotations

import hashlib
import json
import os
import urllib.error
import urllib.request
from decimal import Decimal, InvalidOperation
from urllib.parse import quote

TIMEOUT = float(os.environ.get("ERP_TIMEOUT", "10"))
MANIFEST = {
    "name": "erp_post_invoice",
    "description": "Post an invoice into the internal ERP. Idempotent: same payload = same row.",
    "risk": "write",
    "idempotent": True,
    "requires_approval": True,
    "side_effect_free": False,
    "parameters": {
        "type": "object",
        "additionalProperties": False,
        "required": ["action", "vendor", "company", "amount", "invoice_number", "currency",
                     "due_date", "source_file", "base_url", "idempotency_key"],
        "properties": {
            "action": {"type": "string", "enum": ["post", "list", ""],
                       "description": "post (default) or list"},
            "vendor": {"type": "string"},
            "company": {"type": "string"},
            "amount": {"type": "string", "description": "Decimal string, e.g. '4820.00'"},
            "invoice_number": {"type": "string"},
            "currency": {"type": "string"},
            "due_date": {"type": "string", "description": "ISO date, e.g. 2024-10-12"},
            "source_file": {"type": "string"},
            "base_url": {"type": "string", "description": "Defaults to $ERP_URL"},
            "idempotency_key": {"type": "string", "description": "Defaults to a hash of the payload"},
        },
    },
}


def base_url(override: str | None = None) -> str:
    return (override or os.environ.get("ERP_URL", "http://127.0.0.1:8901")).rstrip("/")


CONTROL = ("base_url", "action", "idempotency_key")


def idempotency_key(payload: dict) -> str:
    """Same invoice content => same key, so a replayed run cannot create a second row."""
    canonical = json.dumps(
        {k: payload[k] for k in sorted(payload) if k not in CONTROL}, separators=(",", ":")
    )
    return "inv-" + hashlib.sha256(canonical.encode()).hexdigest()[:24]


def _request(method: str, url: str, body: dict | None = None, headers: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return {"ok": True, "status": resp.status, "body": json.loads(resp.read() or b"{}")}
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            parsed = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            parsed = {"raw": raw.decode("utf-8", "replace")}
        return {"ok": False, "status": e.code, "body": parsed, "error": parsed.get("error", str(e))}
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        return {"ok": False, "status": None, "error": f"ERP unreachable at {url}: {e}"}


def post_invoice(invoice: dict, base: str | None = None, key: str | None = None) -> dict:
    payload = {k: v for k, v in invoice.items() if k not in CONTROL and v not in (None, "")}
    if not payload.get("amount"):
        return {"ok": False, "status": 422, "error": "missing required field: amount"}
    try:
        payload["amount"] = str(Decimal(str(payload.get("amount", ""))).quantize(Decimal("0.01")))
    except InvalidOperation:
        return {"ok": False, "status": 422, "error": f"amount not a number: {payload.get('amount')!r}"}
    url = f"{base_url(base)}/invoices"
    key = key or idempotency_key(payload)
    res = _request("POST", url, payload, {"Idempotency-Key": key})
    res["idempotency_key"] = key
    return res


def list_invoices(company: str | None = None, base: str | None = None) -> dict:
    # quote: company names have spaces ("Company X") and a raw space is an InvalidURL.
    url = f"{base_url(base)}/invoices" + (f"?company={quote(company)}" if company else "")
    return _request("GET", url)


def run(args: dict) -> dict:
    base = args.get("base_url") or None
    if (args.get("action") or "post") == "list":
        res = list_invoices(args.get("company") or None, base)
    else:
        res = post_invoice(args, base, args.get("idempotency_key") or None)
    res.setdefault("error", None)
    return res
