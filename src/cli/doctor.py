"""doctor: is this machine ready to run the demo? One line per check, plain words, exit 0 = yes.

    python3 -m src.cli.main doctor             # ready for the offline demo? (no network needed)
    python3 -m src.cli.main doctor --browser   # also require the optional Playwright browser path

Offline is the target, not a fallback: a missing sim ERP, a missing API key and a missing
Playwright are all *notes* (the demo starts its own sim and plans heuristically). Only things
that break the offline path are failures. `--browser` promotes Playwright to a failure, because
then you asked for a path that cannot run without it.
"""

from __future__ import annotations

import argparse
import importlib.metadata as meta
import importlib.util
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import NamedTuple

ROOT = Path(__file__).resolve().parents[2]
MIN_PYTHON = (3, 11)
REQUIRED = (("pydantic", "frozen contracts (ToolManifest, Verdict)"),
            ("yaml", "context/company.yaml + policies.yaml"))
OPTIONAL = (("openai", "LLM planner (the demo plans heuristically without it)"),
            ("pytest", "running the test suite"))
FINE = (("playwright", "only the browser path needs it; the demo uses files + ERP"),)


class Check(NamedTuple):
    label: str
    state: str  # ok | note | fail | help
    detail: str


# the one import name that differs from its distribution name; a full packages_distributions()
# walk costs ~0.3s of the doctor's <1s promise for one lookup
DIST_ALIAS = {"yaml": "PyYAML"}


def version_of(module: str) -> str | None:
    try:
        return meta.version(DIST_ALIAS.get(module, module))
    except meta.PackageNotFoundError:
        return None


def say(line: str = "") -> None:
    print(line, flush=True)


def _print(checks: list[Check]) -> int:
    width = max(len(c.label) for c in checks)
    for check in checks:
        say(f"{check.label:<{width}}  {check.state:<5}  {check.detail}")
    return 1 if any(c.state == "fail" for c in checks) else 0


def dep_check(module: str, why: str, state_when_missing: str, *, suggest: bool = False) -> Check:
    """`suggest` is for install advice the caller asked for: absent optional deps are not gaps."""
    if importlib.util.find_spec(module) is None:
        hint = f"; pip install {module}" if suggest else ""
        return Check(module, state_when_missing, f"absent — {why}{hint}")
    return Check(module, "ok", f"{version_of(module) or 'present'} — {why}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python3 -m src.cli.main doctor", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--browser", action="store_true", help="also require the optional browser path")
    args = ap.parse_args(argv)
    checks: list[Check] = []

    # python
    py_ok = sys.version_info[:2] >= MIN_PYTHON
    checks.append(Check("python", "ok" if py_ok else "fail",
                        f"{'.'.join(map(str, sys.version_info[:3]))} "
                        f"(need >= {'.'.join(map(str, MIN_PYTHON))})"))

    # deps: required ones fail (and tell you how to fix it), optional ones are notes
    checks += [dep_check(m, why, "fail", suggest=True) for m, why in REQUIRED]
    checks += [dep_check(m, why, "note") for m, why in OPTIONAL]
    checks += [dep_check(m, why, "fail" if args.browser else "note", suggest=args.browser)
               for m, why in FINE]
    if args.browser and importlib.util.find_spec("playwright") is None:
        checks.append(Check("install", "help", "pip install playwright && playwright install chromium"))

    # context + policy numbers, read through the loader so the demo and the doctor cannot disagree
    try:
        sys.path.insert(0, str(ROOT))
        from src.policy.loader import load_context  # noqa: PLC0415

        ctx = load_context()
        ceiling = float(ctx["policies"]["max_amount_auto_post"])
        checks.append(Check("context", "ok", "company.yaml + policies.yaml + tools.yaml valid"))
        checks.append(Check("policy", "ok",
                            f"auto-post <= {money(ceiling)} unattended; above that a human approves; "
                            f"approval queue = {ctx['company']['approval']['queue']}"))
    except Exception as exc:  # noqa: BLE001 - the message is the deliverable here
        checks.append(Check("context", "fail", f"{type(exc).__name__}: {exc}"))

    # seed data
    invoices = sorted((ROOT / "data" / "seed" / "invoices").glob("*"))
    checks.append(Check("seed", "ok" if invoices else "fail",
                        f"{len(invoices)} invoices in data/seed/invoices"
                        if invoices else "none — next: python3 data/seed/make_pdfs.py"))

    # runs dir writable
    runs = Path(os.environ.get("CENTRALIGN_RUNS", ROOT / "runs"))
    try:
        runs.mkdir(parents=True, exist_ok=True)
        probe = runs / ".doctor-write-probe"
        probe.write_text("", encoding="utf-8")
        probe.unlink()
        checks.append(Check("runs dir", "ok", f"{runs} is writable"))
    except OSError as exc:
        checks.append(Check("runs dir", "fail", f"{runs}: {exc} — pass --runs <writable dir>"))

    # sim ERP reachability: a note, because `demo` starts its own on a scratch db
    base = os.environ.get("ERP_URL", "http://127.0.0.1:8901").rstrip("/")
    if _alive(base):
        count = _count(base)
        checks.append(Check("sim ERP", "ok", f"{base} is up ({count} invoice rows)"))
    else:
        checks.append(Check("sim ERP", "note", f"not running at {base} — fine: the demo starts its own "
                                              f"per run; or: python3 sim_app/server.py --port 8901 --db /tmp/sim.db"))
    checks.append(Check("network", "ok", "not needed: no API key, no internet — only 127.0.0.1 is contacted"))

    say("\nCentrAlign doctor")
    rc = _print(checks)
    say("\nready: the offline demo runs (python3 -m src.cli.main demo)"
        if rc == 0 else "\nnot ready: fix the fail lines above, then re-run doctor")
    return rc


def money(value: float) -> str:
    return f"${value:,.2f}"


def _get(url: str, timeout: float = 2.0) -> dict:
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return json.loads(resp.read() or b"{}")


def _alive(base: str) -> bool:
    try:
        return bool(_get(f"{base}/health").get("ok"))
    except (urllib.error.URLError, OSError, ValueError):
        return False


def _count(base: str) -> int:
    try:
        return int(_get(f"{base}/invoices").get("count", 0))
    except (urllib.error.URLError, OSError, ValueError, TypeError):
        return -1


if __name__ == "__main__":  # `python3 -m src.cli.doctor` also works
    raise SystemExit(main())