"""Top-k facts for a task, via the indexed FTS5 table. No LLM, no scan."""

from __future__ import annotations

import re
from typing import Any

from src.memory.store import Store

TOKEN_RE = re.compile(r"[\w.+-]+")


def _match_query(task: str) -> str:
    """FTS5 MATCH string: OR of quoted tokens. AND would drop the whole row set once the
    task has any word the fact lacks ("what", "are"); bm25 ranks the real matches on top."""
    tokens = [t.replace('"', '""') for t in TOKEN_RE.findall(task)]
    return " OR ".join(f'"{t}"' for t in tokens)


def recall(store: Store, company_id: str, task: str, k: int = 5) -> list[dict[str, Any]]:
    """Return up to k facts for `company_id` ranked by FTS5 bm25 (lower score = better)."""
    query = _match_query(task)
    if not query:
        return store.facts(company_id, limit=k)
    rows = store.conn.execute(
        "SELECT f.id, f.category, f.key, f.value, f.source, f.redacted, f.created_at, bm25(facts_fts) AS score"
        " FROM facts_fts JOIN facts f ON f.id = facts_fts.rowid"
        " WHERE facts_fts MATCH ? AND f.company_id = ?"
        " ORDER BY score, f.id LIMIT ?",
        (query, company_id, k),
    )
    return [dict(row) for row in rows]