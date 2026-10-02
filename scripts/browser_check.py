#!/usr/bin/env python3
"""Browser check: drive the sim ERP's invoice portal in a real headless chromium.

    python3 scripts/browser_check.py            # PASS with playwright installed
    python3 scripts/browser_check.py            # SKIP (rc 0) when playwright is absent
    python3 scripts/browser_check.py --help     # nothing else to pass: there are no options

What it proves, in one command:
  * the negative case — `https://evil.com/` is refused by the allowlist, and refused *before*
    any browser is launched (no Chromium process, no request)
  * the positive case — a real chromium loads http://127.0.0.1:<port>/portal, finds the title
    and every seeded invoice, and leaves a screenshot on disk

The sim ERP is spawned on a scratch database under /tmp and stopped again on the way out, the
same way `bash demo/run.sh` does it. Nothing outside /tmp is written or deleted, and the only
host contacted is 127.0.0.1.

Playwright is an optional dependency: without it this script says so in plain words and exits 0,
because "the browser is not installed" is not a failure of the system it is checking.

Refs: https://playwright.dev/python/docs/library (sync API, auto-wait, no sleeps anywhere).
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.tools import browser_tool  # noqa: E402

SCRATCH = Path("/tmp/centralign-browser")
SEED_DIR = ROOT / "data" / "seed" / "invoices"
BANNER = "CentrAlign browser check · localhost only · scratch /tmp/centralign-browser"


def say(line: str = "") -> None:
    print(line, flush=True)


def ok(label: str, detail: str) -> None:
    say(f"  ✓ {label:<22} {detail}")


def check_allowlist() -> None:
    """Refuse an off-allowlist URL, and prove no browser was started to do it.

    This runs before `sync_playwright()`, so a regression that checked the host *after*
    launching would show up as an assertion failure on `_STATE`, not as a slow test.
    """
    for bad in ("https://evil.com/portal", "https://example.com.evil.com/portal", "file:///etc/passwd"):
        try:
            browser_tool.check_url(bad)
        except browser_tool.UrlNotAllowed:
            continue
        raise AssertionError(f"allowlist let {bad} through")
    assert "context" not in browser_tool._STATE, "a browser was launched before the URL was checked"
    ok("allowlist", "evil.com, the suffix trick and file:// refused, no browser launched")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python3 scripts/browser_check.py", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.parse_args(argv)
    say(BANNER)

    check_allowlist()

    try:
        from playwright.sync_api import sync_playwright  # noqa: PLC0415 - optional dep
    except ImportError:
        say("\nSKIP: playwright is not installed, so there is no browser to drive. Nothing is wrong "
            "with CentrAlign — every other claim in README.md runs offline without it.\n"
            "      to run this check anyway:  pip install playwright && python3 -m playwright install chromium")
        return 0

    seeded = sorted(p.name for p in SEED_DIR.glob("*"))
    if not seeded:
        say(f"\nFAIL: no seed invoices in {SEED_DIR} — next: python3 data/seed/make_pdfs.py")
        return 1

    if SCRATCH.exists():
        shutil.rmtree(SCRATCH)
    db = SCRATCH / "sim.db"
    # straight under /tmp: this script drives Playwright itself, so the data/ sandbox that
    # browser_tool enforces on *agent* screenshot paths does not apply to the scratch here.
    shot = SCRATCH / "portal.png"

    from src.cli.main import free_port, start_sim, wait_sim  # noqa: PLC0415 - the demo's own spawner

    port = free_port()
    base = f"http://127.0.0.1:{port}"
    proc = start_sim(db, port)
    try:
        if not wait_sim(base, db, proc):
            say(f"\nFAIL: the sim ERP did not come up at {base}")
            say(f"      next: python3 sim_app/server.py --port {port} --db {db}")
            return 1
        say(f"\nsim ERP   {base}  db={db}  (started for this check, stopped when it ends)")
        try:
            with sync_playwright() as pw:  # every Playwright call auto-waits; no sleeps anywhere
                browser = pw.chromium.launch(headless=True)
                page = browser.new_page()
                try:
                    resp = page.goto(f"{base}/portal", wait_until="domcontentloaded")
                    page.wait_for_selector("#invoices li")
                    title = page.inner_text("#title").strip()
                    listed = page.locator("#invoices li").all_inner_texts()
                    counted = page.inner_text("#count").strip()
                    shot.parent.mkdir(parents=True, exist_ok=True)
                    page.screenshot(path=str(shot), full_page=True)
                finally:
                    page.close()
                    browser.close()
        except Exception as exc:  # noqa: BLE001 - the message is the deliverable here
            say(f"\nFAIL: chromium could not drive the portal: {type(exc).__name__}: {exc}")
            if "Executable doesn't exist" in str(exc) or "playwright install" in str(exc):
                say("      next: python3 -m playwright install chromium")
            return 1

        assert resp is not None and resp.status == 200, f"GET /portal answered {resp}"
        ok("portal loads", f"HTTP 200, title {title!r}")
        assert title == "Acme portal — inbox", f"unexpected title: {title!r}"
        assert len(listed) == len(seeded), f"portal lists {len(listed)}, seed dir holds {len(seeded)}"
        assert len(listed) == 3, f"expected the 3 seeded invoices, portal lists {len(listed)}"
        assert counted == str(len(seeded)), f"portal claims {counted} files, seed dir holds {len(seeded)}"
        ok("3 invoices listed", ", ".join(name.split("-", 2)[-1] for name in listed))
        ok("screenshot", str(shot))
        say("\nPASS: the portal rendered in a real browser, the allowlist refused evil.com "
            "without launching one, and the screenshot is on disk.")
        return 0
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:  # noqa: BLE001 - a wedged sim server must not mask the verdict
            proc.kill()


if __name__ == "__main__":
    raise SystemExit(main())