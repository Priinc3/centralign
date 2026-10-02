"""Append-only SQLite WAL ledger for runs, steps and events.

Single writer per process: one connection, WAL, busy_timeout.
Refs: https://www.sqlite.org/wal.html
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import uuid
from pathlib import Path
from typing import Any

from ..contracts.events import Event, redact, utc_now

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id      TEXT PRIMARY KEY,
    task        TEXT NOT NULL,
    goal        TEXT,
    status      TEXT NOT NULL,            -- running|completed|failed|blocked
    stage       TEXT,
    offline     INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    verdict     TEXT,                     -- json Verdict
    evidence_dir TEXT
);
-- Append-only: one row per step *attempt*, never updated. A retry appends attempt N+1.
CREATE TABLE IF NOT EXISTS steps (
    idem_key      TEXT NOT NULL,
    run_id        TEXT NOT NULL,
    step_id       TEXT NOT NULL,
    seq           INTEGER NOT NULL,
    tool          TEXT NOT NULL,
    args          TEXT NOT NULL,
    depends_on    TEXT NOT NULL DEFAULT '[]',
    status        TEXT NOT NULL,          -- succeeded|failed|skipped|cached
    result        TEXT,
    error         TEXT,
    attempt       INTEGER NOT NULL DEFAULT 1,
    started_at    TEXT NOT NULL,
    ended_at      TEXT NOT NULL,
    UNIQUE (run_id, step_id, attempt)
);
-- Idempotency index: a (tool, args) pair that already succeeded is replayed, not re-executed.
CREATE INDEX IF NOT EXISTS steps_idem_key_idx ON steps(idem_key, status);
CREATE TABLE IF NOT EXISTS events (
    run_id  TEXT NOT NULL,
    seq     INTEGER NOT NULL,
    ts      TEXT NOT NULL,
    type    TEXT NOT NULL,
    actor   TEXT NOT NULL,
    step_id TEXT,
    tool    TEXT,
    payload TEXT NOT NULL,
    error   TEXT,
    PRIMARY KEY (run_id, seq)
);
CREATE INDEX IF NOT EXISTS events_run_ts ON events(run_id, ts);
"""

def idem_key(tool: str, args: dict[str, Any]) -> str:
    """Stable content hash of (tool, args): replan/retry replays instead of re-executing."""
    blob = json.dumps({"tool": tool, "args": redact(args)}, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode()).hexdigest()[:32]


def new_run_id() -> str:
    return uuid.uuid4().hex[:12]


class Ledger:
    def __init__(self, path: str | os.PathLike[str], *, run_root: str | os.PathLike[str] | None = None) -> None:
        self.path = Path(path)
        self.run_root = Path(run_root) if run_root else self.path.parent
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.path), isolation_level=None, timeout=5.0)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(
            f"PRAGMA journal_mode=WAL;\nPRAGMA synchronous=NORMAL;\nPRAGMA busy_timeout=5000;\nPRAGMA foreign_keys=ON;\n{SCHEMA}"
        )

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> Ledger:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # ---- runs -------------------------------------------------------------
    def start_run(self, run_id: str, task: str, *, goal: str | None = None, offline: bool = False) -> None:
        now = utc_now()
        self.conn.execute(
            "INSERT INTO runs (run_id, task, goal, status, stage, offline, created_at, updated_at)"
            " VALUES (?,?,?, 'running', 'goal', ?, ?, ?)",
            (run_id, task, goal, int(offline), now, now),
        )

    def set_stage(self, run_id: str, stage: str) -> None:
        self.conn.execute("UPDATE runs SET stage=?, updated_at=? WHERE run_id=?", (stage, utc_now(), run_id))

    def finish_run(
        self,
        run_id: str,
        status: str,
        *,
        verdict: dict[str, Any] | None = None,
        evidence_dir: str | None = None,
    ) -> None:
        self.conn.execute(
            "UPDATE runs SET status=?, updated_at=?, verdict=?, evidence_dir=? WHERE run_id=?",
            (status, utc_now(), json.dumps(verdict) if verdict else None, evidence_dir, run_id),
        )

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
        return dict(row) if row else None

    # ---- steps (append-only: one row per attempt, no updates) ------------
    def append_step(self, step: dict[str, Any]) -> None:
        # F3: an attempt number is never re-used, so a re-record is data rather than an
        # IntegrityError escaping the executor's own error path (Phase 04 HELP-2).
        row = self.conn.execute(
            "SELECT COALESCE(MAX(attempt), 0) FROM steps WHERE run_id=? AND step_id=?",
            (step["run_id"], step["step_id"]),
        ).fetchone()
        if int(step.get("attempt", 1)) <= int(row[0]):
            step = {**step, "attempt": int(row[0]) + 1}
        self.conn.execute(
            "INSERT INTO steps (idem_key, run_id, step_id, seq, tool, args, depends_on, status, result, error,"
            " attempt, started_at, ended_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                step["idem_key"],
                step["run_id"],
                step["step_id"],
                step["seq"],
                step["tool"],
                json.dumps(step.get("args", {}), sort_keys=True, default=str),
                json.dumps(step.get("depends_on", [])),
                step["status"],
                json.dumps(step.get("result"), default=str) if step.get("result") is not None else None,
                step.get("error"),
                step.get("attempt", 1),
                step.get("started_at") or utc_now(),
                step.get("ended_at") or utc_now(),
            ),
        )

    def steps_for_run(self, run_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM steps WHERE run_id=? ORDER BY seq, attempt", (run_id,)
        ).fetchall()
        return [_decode_step(dict(r)) for r in rows]

    def find_by_idem(self, idem_key: str) -> dict[str, Any] | None:
        """Latest successful execution of this (tool, args) pair in any run, if any.

        A row whose result payload is an {ok: false} envelope is not a success, however it was
        written (rows predate the executor checking `ok`): never replay one, re-execute instead.
        """
        row = self.conn.execute(
            "SELECT * FROM steps WHERE idem_key=? AND status IN ('succeeded','cached')"
            " ORDER BY attempt DESC, rowid DESC LIMIT 1",
            (idem_key,),
        ).fetchone()
        if row is None:
            return None
        step = _decode_step(dict(row))
        if isinstance(step["result"], dict) and step["result"].get("ok") is False:
            return None
        return step

    # ---- events (append-only) --------------------------------------------
    def append_event(self, event: Event) -> Event:
        """Assign the next per-run seq, store, and return the event with seq set."""
        row = self.conn.execute("SELECT COALESCE(MAX(seq), -1) AS s FROM events WHERE run_id=?", (event.run_id,)).fetchone()
        stored = event.model_copy(update={"seq": int(row["s"]) + 1})
        self.conn.execute(
            "INSERT INTO events (run_id, seq, ts, type, actor, step_id, tool, payload, error) VALUES (?,?,?,?,?,?,?,?,?)",
            (
                stored.run_id,
                stored.seq,
                stored.ts,
                stored.type,
                stored.actor,
                stored.step_id,
                stored.tool,
                json.dumps(stored.payload, sort_keys=True, default=str),
                stored.error,
            ),
        )
        return stored

    def events_for_run(self, run_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute("SELECT * FROM events WHERE run_id=? ORDER BY seq", (run_id,)).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["payload"] = json.loads(d["payload"])
            out.append(d)
        return out

    def count_events(self, run_id: str, type: str | None = None) -> int:
        if type is None:
            row = self.conn.execute("SELECT COUNT(*) c FROM events WHERE run_id=?", (run_id,)).fetchone()
        else:
            row = self.conn.execute(
                "SELECT COUNT(*) c FROM events WHERE run_id=? AND type=?", (run_id, type)
            ).fetchone()
        return int(row["c"])


def _decode_step(row: dict[str, Any]) -> dict[str, Any]:
    for key in ("args", "depends_on", "result"):
        raw = row.get(key)
        if raw is None:
            row[key] = None if key != "depends_on" else []
        elif key == "result":
            try:
                row[key] = json.loads(raw)
            except (TypeError, ValueError):
                row[key] = raw
        else:
            row[key] = json.loads(raw)
    return row
