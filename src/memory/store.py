"""Persistent company memory: SQLite in WAL mode, single writer, redacted facts.

Refs: https://www.sqlite.org/wal.html
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from src.policy.loader import ROOT, load_context

DEFAULT_DB = ROOT / "data" / "memory.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS companies (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS facts (
  id INTEGER PRIMARY KEY,
  company_id TEXT NOT NULL REFERENCES companies(id),
  category TEXT NOT NULL,
  key TEXT NOT NULL,
  value TEXT NOT NULL,
  text TEXT NOT NULL,               -- what FTS5 indexes
  source TEXT NOT NULL DEFAULT '',
  redacted INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS facts_company_category ON facts(company_id, category);
CREATE TABLE IF NOT EXISTS runs (
  run_id TEXT PRIMARY KEY,
  company_id TEXT NOT NULL,
  task TEXT NOT NULL,
  status TEXT NOT NULL,
  summary TEXT NOT NULL DEFAULT '',
  started_at TEXT NOT NULL,
  ended_at TEXT
);
CREATE INDEX IF NOT EXISTS runs_company ON runs(company_id, started_at);
CREATE VIRTUAL TABLE IF NOT EXISTS facts_fts USING fts5(text, content='facts', content_rowid='id');
CREATE TRIGGER IF NOT EXISTS facts_ai AFTER INSERT ON facts BEGIN
  INSERT INTO facts_fts(rowid, text) VALUES (new.id, new.text);
END;
CREATE TRIGGER IF NOT EXISTS facts_ad AFTER DELETE ON facts BEGIN
  INSERT INTO facts_fts(facts_fts, rowid, text) VALUES ('delete', old.id, old.text);
END;
CREATE TRIGGER IF NOT EXISTS facts_au AFTER UPDATE ON facts BEGIN
  INSERT INTO facts_fts(facts_fts, rowid, text) VALUES ('delete', old.id, old.text);
  INSERT INTO facts_fts(rowid, text) VALUES (new.id, new.text);
END;
"""

# One writer at a time: SQLite allows many readers in WAL, but writes serialise anyway.
# This lock makes "single writer" explicit for our own threads instead of relying on
# busy_timeout alone. ponytail: swap for a real IPC queue if a second process ever writes.
_WRITE_LOCK = threading.Lock()


class Store:
    def __init__(
        self,
        path: Path | str = DEFAULT_DB,
        redactor: Callable[[str], tuple[str, list[str]]] | None = None,
    ) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._redact = redactor if redactor is not None else load_context()["redactor"]
        self.conn = sqlite3.connect(self.path, isolation_level=None, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self.conn.execute("PRAGMA busy_timeout=5000")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.executescript(SCHEMA)
        self._sync_fts()

    def _sync_fts(self) -> None:
        """Rebuild the index only if it drifted (external-content FTS5)."""
        facts = self.conn.execute("SELECT count(*) FROM facts").fetchone()[0]
        indexed = self.conn.execute("SELECT count(*) FROM facts_fts").fetchone()[0]
        if facts != indexed:
            self.conn.execute("INSERT INTO facts_fts(facts_fts) VALUES ('rebuild')")

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "Store":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def add_company(self, company_id: str, name: str = "") -> None:
        with _WRITE_LOCK, self.conn:
            self.conn.execute(
                "INSERT INTO companies (id, name, created_at) VALUES (?, ?, ?) ON CONFLICT(id) DO UPDATE SET name=excluded.name",
                (company_id, name or company_id, _now()),
            )

    def remember(
        self, company_id: str, category: str, key: str, value: str, source: str = ""
    ) -> int:
        """Store one fact. Value is PII-redacted before it ever hits disk."""
        clean, hits = self._redact(str(value))
        text = " ".join(part for part in (category, key, clean, source) if part)
        with _WRITE_LOCK, self.conn:
            cur = self.conn.execute(
                "INSERT INTO facts (company_id, category, key, value, text, source, redacted, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (company_id, category, key, clean, text, source, int(bool(hits)), _now()),
            )
        return int(cur.lastrowid)

    def facts(self, company_id: str, limit: int = 50) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT id, category, key, value, source, redacted, created_at FROM facts"
            " WHERE company_id = ? ORDER BY id DESC LIMIT ?",
            (company_id, limit),
        )
        return [dict(row) for row in rows]

    def start_run(self, run_id: str, company_id: str, task: str) -> None:
        with _WRITE_LOCK, self.conn:
            self.conn.execute(
                "INSERT INTO runs (run_id, company_id, task, status, started_at) VALUES (?, ?, ?, 'running', ?)",
                (run_id, company_id, task, _now()),
            )

    def finish_run(self, run_id: str, status: str, summary: str = "") -> None:
        with _WRITE_LOCK, self.conn:
            self.conn.execute(
                "UPDATE runs SET status = ?, summary = ?, ended_at = ? WHERE run_id = ?",
                (status, summary, _now(), run_id),
            )

    def runs(self, company_id: str, limit: int = 50) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT run_id, task, status, summary, started_at, ended_at FROM runs"
            " WHERE company_id = ? ORDER BY started_at DESC LIMIT ?",
            (company_id, limit),
        )
        return [dict(row) for row in rows]

    def pragma(self, name: str) -> Any:
        return self.conn.execute(f"PRAGMA {name}").fetchone()[0]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")