"""Sim ERP: stdlib http.server + SQLite. No web framework (ponytail rung 3).

Endpoints
  GET  /health
  GET  /portal                     HTML index of seed invoices (browser_tool target)
  GET  /invoices[?company=]        list
  GET  /invoices/<id>              one
  POST /invoices                    create; Idempotency-Key header => repeat POST returns the same row

Run: python sim_app/server.py --port 8901
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sqlite3
import sys
from decimal import Decimal, InvalidOperation
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCHEMA = pathlib.Path(__file__).resolve().parent / "schema.sql"
DEFAULT_DB = ROOT / "data" / "sim_erp.db"
INVOICE_DIR = ROOT / "data" / "seed" / "invoices"
FIELDS = ("vendor", "company", "invoice_number", "amount", "currency", "due_date", "source_file")


def connect(db: str | pathlib.Path) -> sqlite3.Connection:
    path = pathlib.Path(db)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=5)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA.read_text())
    return conn


class Handler(BaseHTTPRequestHandler):
    db: str = str(DEFAULT_DB)
    server_version = "SimERP/1.0"

    # --- plumbing -------------------------------------------------------
    def _send(self, code: int, payload: dict | str, ctype: str = "application/json") -> None:
        body = payload.encode() if isinstance(payload, str) else json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", f"{ctype}; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *a) -> None:  # keep test output clean
        if self.server.verbose:  # type: ignore[attr-defined]
            sys.stderr.write("sim_erp " + fmt % a + "\n")

    # --- routes ---------------------------------------------------------
    def do_GET(self) -> None:
        url = urlparse(self.path)
        path, query = url.path.rstrip("/") or "/", parse_qs(url.query)
        conn = connect(self.db)
        try:
            if path in ("/", "/health"):
                return self._send(200, {"ok": True, "service": "sim-erp", "db": self.db})
            if path == "/portal":
                return self._send(200, _portal_html(), "text/html")
            if path == "/invoices":
                where, args = "", []
                if "company" in query:
                    where, args = "WHERE company = ?", [query["company"][0]]
                rows = conn.execute(
                    f"SELECT * FROM invoices {where} ORDER BY id DESC", args
                ).fetchall()
                return self._send(200, {"count": len(rows), "invoices": [dict(r) for r in rows]})
            if path.startswith("/invoices/"):
                row = conn.execute(
                    "SELECT * FROM invoices WHERE id = ?", (int(path.rsplit("/", 1)[1]),)
                ).fetchone()
                return self._send(200, dict(row)) if row else self._send(404, {"error": "not found"})
            self._send(404, {"error": "no such route", "path": path})
        finally:
            conn.close()

    def do_POST(self) -> None:
        if urlparse(self.path).path.rstrip("/") != "/invoices":
            return self._send(404, {"error": "no such route"})
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        except json.JSONDecodeError as e:
            return self._send(400, {"error": f"bad json: {e}"})
        if not isinstance(body, dict):
            return self._send(400, {"error": "body must be a JSON object"})

        missing = [f for f in ("vendor", "company", "amount") if not str(body.get(f, "")).strip()]
        if missing:
            return self._send(422, {"error": f"missing required fields: {missing}"})
        try:
            amount = str(Decimal(str(body["amount"])).quantize(Decimal("0.01")))
        except InvalidOperation:
            return self._send(422, {"error": f"amount not a number: {body['amount']!r}"})

        key = self.headers.get("Idempotency-Key") or body.get("idempotency_key")
        if not key:
            return self._send(400, {"error": "Idempotency-Key header required"})

        payload = {f: (amount if f == "amount" else str(body.get(f) or "")) for f in FIELDS}
        payload["amount"], payload["currency"] = amount, payload["currency"] or "USD"
        cols = ", ".join(["idempotency_key", *FIELDS])
        marks = ", ".join("?" * (len(FIELDS) + 1))
        conn = connect(self.db)
        try:
            cur = conn.execute(
                f"INSERT OR IGNORE INTO invoices ({cols}) VALUES ({marks})", (key, *payload.values())
            )
            row = conn.execute("SELECT * FROM invoices WHERE idempotency_key = ?", (key,)).fetchone()
            conn.commit()
        finally:
            conn.close()
        out = dict(row)
        out["created"] = bool(cur.rowcount)
        self._send(201 if out["created"] else 200, out)


def _portal_html() -> str:
    links = "".join(
        f'<li><a href="/invoices/{p.stem}">{p.name}</a> — {p.stat().st_size} bytes</li>'
        for p in sorted(INVOICE_DIR.glob("*"))
    )
    return (
        "<!doctype html><html><head><meta charset='utf-8'><title>Invoice portal</title></head>"
        "<body><h1 id='title'>Acme portal — inbox</h1>"
        f"<ul id='invoices'>{links}</ul>"
        "<p>Total files: <span id='count'>%d</span></p></body></html>"
        % len(list(INVOICE_DIR.glob("*")))
    )


def make_server(host: str = "127.0.0.1", port: int = 8901, db: str | pathlib.Path = DEFAULT_DB,
                verbose: bool = False) -> ThreadingHTTPServer:
    handler = type("BoundHandler", (Handler,), {"db": str(db)})
    srv = ThreadingHTTPServer((host, port), handler)
    srv.verbose = verbose  # type: ignore[attr-defined]
    return srv


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Sim ERP server")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8901)
    ap.add_argument("--db", default=str(DEFAULT_DB))
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args()
    s = make_server(a.host, a.port, a.db, a.verbose)
    print(f"sim-erp on http://{a.host}:{a.port}  db={a.db}", flush=True)
    try:
        s.serve_forever()
    except KeyboardInterrupt:
        s.shutdown()
