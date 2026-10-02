"""Browser tool: Playwright sync API, chromium only, URL allowlist, auto-wait (no sleeps).

Playwright is imported lazily and the browser is launched once per process and reused, so
importing this module (and the allowlist test) never needs the dependency installed.
"""

from __future__ import annotations

import os
from urllib.parse import urlsplit

from .files_tool import safe_path

DEFAULT_ALLOWLIST = "localhost,127.0.0.1"
SCHEMES = ("http", "https")
LOOPBACK = ("localhost", "127.0.0.1", "::1")

_STATE: dict = {}

MANIFEST = {
    "name": "browser_open",
    "description": "Open an allowlisted URL in headless chromium, auto-wait for a selector, "
                   "optionally screenshot into data/ and read a selector's text.",
    "risk": "read",
    "idempotent": True,
    "requires_approval": False,
    "side_effect_free": True,
    "parameters": {
        "type": "object",
        "additionalProperties": False,
        "required": ["url", "wait_for", "text", "screenshot"],
        "properties": {
            "url": {"type": "string", "description": "http(s) URL on an allowlisted host"},
            "wait_for": {"type": "string", "description": "CSS selector to auto-wait for"},
            "text": {"type": "string", "description": "CSS selector whose text to return"},
            "screenshot": {"type": "string", "description": "Path under data/ for a PNG"},
        },
    },
}


class UrlNotAllowed(PermissionError):
    pass


def allowlist() -> list[str]:
    """ALLOWLIST=localhost,example.com — read per call so tests can monkeypatch the env."""
    raw = os.environ.get("ALLOWLIST", DEFAULT_ALLOWLIST)
    return [h.strip().lower().lstrip(".") for h in raw.split(",") if h.strip()]


def check_url(url: str, allowed: list[str] | None = None) -> str:
    """Return the normalized URL or raise UrlNotAllowed. The only egress chokepoint."""
    parts = urlsplit(url.strip())
    host = (parts.hostname or "").lower()
    if parts.scheme not in SCHEMES or not host:
        raise UrlNotAllowed(f"only http(s) URLs allowed: {url!r}")
    # loopback never leaves the machine, so it stays reachable even on a tight allowlist.
    if host in LOOPBACK or any(host == a or host.endswith("." + a) for a in (allowed or allowlist())):
        return parts.geturl()
    raise UrlNotAllowed(f"host not on ALLOWLIST={','.join(allowed or allowlist())}: {host}")


def _context():
    if "context" not in _STATE:
        from playwright.sync_api import sync_playwright  # lazy: keeps import cost + deps optional

        _STATE["pw_cm"] = sync_playwright()
        _STATE["browser"] = _STATE["pw_cm"].start().chromium.launch(headless=True)
        _STATE["context"] = _STATE["browser"].new_context()
    return _STATE["context"]


def close() -> None:
    """Teardown. ponytail: `Playwright.stop()` is broken after `.start()` (it routes to a
    `__exit__` with no exit function, so it raises NoneType-not-callable), so keep the
    context manager and exit that. Drop `pw` from _STATE once this runs."""
    for key in ("context", "browser"):
        obj = _STATE.pop(key, None)
        if obj is not None:
            obj.close()
    cm = _STATE.pop("pw_cm", None)
    if cm is not None:
        cm.__exit__(None, None, None)


def open_url(url: str, wait_for: str | None = None, text: str | None = None,
             screenshot: str | None = None) -> dict:
    safe = check_url(url)
    shot = safe_path(screenshot) if screenshot else None
    page = _context().new_page()  # auto-waits on every Playwright call; no time.sleep anywhere
    try:
        resp = page.goto(safe, wait_until="domcontentloaded")
        if wait_for:
            page.wait_for_selector(wait_for, timeout=10_000)
        out = {
            "ok": True,
            "url": page.url,
            "title": page.title(),
            "status": resp.status if resp else None,
            "text": page.inner_text(text).strip() if text else None,
            "screenshot": str(shot) if shot else None,
        }
        if shot:
            shot.parent.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(shot))
        return out
    finally:
        page.close()


def run(args: dict) -> dict:
    try:
        return open_url(
            args["url"], args.get("wait_for"), args.get("text"), args.get("screenshot")
        )
    except UrlNotAllowed as e:
        return {"ok": False, "error": str(e), "blocked_by": "allowlist"}
