"""Filesystem tool, sandboxed to data/. Rejects absolute paths, .. and symlink escapes."""

from __future__ import annotations

import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
DATA = (ROOT / "data").resolve()
MAX_READ_BYTES = 2_000_000

MANIFEST = {
    "name": "files_read",
    "description": "Read a text/PDF file from the sandboxed data/ directory.",
    "risk": "read",
    "idempotent": True,
    "requires_approval": False,
    "side_effect_free": True,
    "parameters": {
        "type": "object",
        "additionalProperties": False,
        "required": ["path", "max_bytes"],
        "properties": {
            "path": {"type": "string", "description": "Path relative to data/, e.g. 'seed/invoices/x.pdf'"},
            "max_bytes": {"type": "integer", "description": f"Read cap, default {MAX_READ_BYTES}"},
        },
    },
}

LIST_MANIFEST = {
    **MANIFEST,
    "name": "files_list",
    "description": "List files in the sandboxed data/ directory.",
    "parameters": {
        "type": "object",
        "additionalProperties": False,
        "required": ["dir", "pattern"],
        "properties": {
            "dir": {"type": "string", "description": "Path relative to data/, default '.'"},
            "pattern": {"type": "string", "description": "Glob, default '*'"},
        },
    },
}


def safe_path(rel: str) -> pathlib.Path:
    """Resolve rel inside data/ or raise. The one chokepoint every file tool call goes through."""
    if not rel or rel.startswith(("/", "~")) or "\x00" in rel:
        raise ValueError(f"path must be relative to data/: {rel!r}")
    p = (DATA / rel).resolve()
    if not p.is_relative_to(DATA):
        raise ValueError(f"path escapes data/ sandbox: {rel!r}")
    return p


def list_files(directory: str = ".", pattern: str = "*") -> dict:
    d = safe_path(directory)
    if not d.is_dir():
        raise FileNotFoundError(f"not a directory: {directory}")
    files = [
        {"name": f.name, "path": str(f.relative_to(DATA)), "bytes": f.stat().st_size}
        for f in sorted(d.glob(pattern))
        if f.is_file()
    ]
    return {"dir": str(d.relative_to(DATA)) or ".", "count": len(files), "files": files}


def read_file(rel: str, max_bytes: int = MAX_READ_BYTES) -> dict:
    p = safe_path(rel)
    if not p.is_file():
        raise FileNotFoundError(f"no such file: {rel}")
    raw = p.read_bytes()[:max_bytes]
    return {
        "path": str(p.relative_to(DATA)),
        "bytes": len(raw),
        "truncated": p.stat().st_size > len(raw),
        "content": raw.decode("utf-8", "replace"),
    }


def run(args: dict) -> dict:
    return {"ok": True, **read_file(args["path"], int(args.get("max_bytes") or MAX_READ_BYTES))}


def run_list(args: dict) -> dict:
    # strict mode sends "" for optional args, so `or` (not .get's default) restores real defaults.
    return {"ok": True, **list_files(args.get("dir") or ".", args.get("pattern") or "*")}
