"""CLI: the one command an evaluator runs.

    python3 -m src.cli.main demo            # seeded invoice -> approval -> ERP post -> evidence
    python3 -m src.cli.main run --task "…"  # any task, with the HITL gate wired
    python3 -m src.cli.main doctor          # is this machine ready? (exit 0 = yes, offline too)

The banner prints before the heavy imports, so the first line lands in well under a second. Every
step line comes from the live ledger (`src/ledger/store.py`) as it is appended, so what you read
while it runs is what ends up in `evidence.json` — and `replayed=N` sits next to the verdict
because a pass served from the idempotency index is not the same claim as a pass that executed.

Nothing here re-implements the loop: `run_task`/`checkpoint.resume` do the work, and the only
Phase 05 wiring is passing `authorizer=hitl.authorizer` (01 FIX-2 HELP-5).
"""

from __future__ import annotations

import argparse
import functools
import getpass
import json
import os
import shutil
import socket
import sqlite3
import subprocess
import sys
import threading
import time
import traceback
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[2]
LEDGER_NAME = "_ledger.sqlite3"
SCRATCH = Path(os.environ.get("CENTRALIGN_SCRATCH", "/tmp/centralign-demo"))
DEFAULT_TASK = "find latest invoice from Company X and post it to the ERP"
BANNER = "CentrAlign · AI operator for invoice intake · offline, no API key needed"
GLYPH = {"succeeded": "✓", "cached": "↻", "skipped": "⏸", "failed": "✗"}


# --------------------------------------------------------------------- output
def say(line: str = "") -> None:
    print(line, flush=True)


def head(label: str, value: str) -> None:
    say(f"{label:<11} {value}")


def money(value: Any) -> str:
    try:
        return f"${float(value):,.2f}"
    except (TypeError, ValueError):
        return str(value)


def approver_name() -> str:
    try:
        return getpass.getuser() or "operator"
    except Exception:  # noqa: BLE001 - a container with no passwd entry is still a demo
        return "operator"


# ------------------------------------------------------------------ the sim ERP
def health(base: str, timeout: float = 1.5) -> dict[str, Any] | None:
    """The sim ERP's /health payload, or None when nothing is answering."""
    try:
        with urllib.request.urlopen(f"{base}/health", timeout=timeout) as resp:
            body = json.loads(resp.read() or b"{}")
        return body if body.get("ok") is True else None
    except (urllib.error.URLError, OSError, ValueError):
        return None


def erp_count(base: str) -> int | None:
    try:
        with urllib.request.urlopen(f"{base}/invoices", timeout=3) as resp:
            return int(json.loads(resp.read() or b"{}").get("count", 0))
    except (urllib.error.URLError, OSError, ValueError, TypeError):
        return None


def free_port() -> int:
    """Ask the OS for an unused port. A hard-coded 8901 collides with a sim the user already runs."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def start_sim(db: Path, port: int) -> subprocess.Popen:
    db.parent.mkdir(parents=True, exist_ok=True)
    return subprocess.Popen(  # noqa: S603 - our own script, fixed argv, no shell
        [sys.executable, str(ROOT / "sim_app" / "server.py"), "--port", str(port), "--db", str(db)],
        cwd=str(ROOT), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


def wait_sim(base: str, db: Path, proc: subprocess.Popen | None = None, timeout: float = 20.0) -> bool:
    """Bounded poll of a localhost socket — a subprocess has to finish booting. No fixed sleep.

    `/health` names the db it is serving, so "something else already owns this port" cannot pass
    for ours: the demo would otherwise post invoices into a stranger's ERP.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        body = health(base, timeout=0.5)
        if body is not None:
            return str(body.get("db")) == str(db)
        if proc is not None and proc.poll() is not None:
            return False
        time.sleep(0.03)
    return False


# --------------------------------------------------------------- step progress
def _detail(row: dict[str, Any]) -> str:
    """One honest line per step: what the tool actually returned, or why it did not run."""
    error = str(row.get("error") or "")
    if error:
        # ponytail: cosmetic. The frozen executor words this "no approval channel in Phase 01",
        # which the CLI makes untrue — the queue is right there. The raw text stays in evidence.json.
        if error.startswith("blocked: approval required"):
            return "not posted — waiting for a human to approve it (queued below)"
        return error
    res = row.get("result")
    if not isinstance(res, dict):
        return ""
    latest = res.get("latest")
    if isinstance(latest, dict):
        return (f"{latest.get('invoice_number')}  {money(latest.get('amount'))} {latest.get('currency')}"
                f"  due {latest.get('due')}")
    body = res.get("body")
    if isinstance(body, dict) and body.get("id"):
        return f"ERP row #{body['id']} " + ("created" if body.get("created") else "already posted (idempotent)")
    return str(res.get("error") or "")


class Follower:
    """Print every step row the moment the ledger appends it (40ms poll of an append-only table).

    ponytail: a reader thread instead of a progress callback, because the loop is frozen (01) and
    the ledger already holds the truth. `run_id=None` follows the newest run it has not seen
    before, which is how a resume gets its progress without knowing its run_id in advance.
    """

    def __init__(self, ledger: Path, run_id: str | None = None, *, avoid: set[str] | None = None,
                 poll: float = 0.04) -> None:
        self.ledger, self.run_id, self.avoid = ledger, run_id, avoid or set()
        self.poll = poll
        self._stop = threading.Event()
        self._seen = 0
        self._conn: sqlite3.Connection | None = None
        self._thread: threading.Thread | None = None

    def _connect(self) -> bool:
        if self._conn is not None:
            return True
        if not self.ledger.is_file():  # the run creates it; a fast run may be over before we look
            return False
        try:
            # check_same_thread: the reader thread opens it, __exit__ does the last drain. Never concurrent.
            self._conn = sqlite3.connect(str(self.ledger), timeout=2.0, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
        except sqlite3.Error:
            return False
        return True

    def _drain(self) -> None:
        if self._conn is None or self.run_id is None:
            return
        try:
            rows = self._conn.execute(
                "SELECT rowid, step_id, tool, status, result, error FROM steps"
                " WHERE run_id=? AND rowid>? ORDER BY rowid", (self.run_id, self._seen),
            ).fetchall()
        except sqlite3.Error:
            return
        for row in rows:
            self._seen = row["rowid"]
            try:
                result = json.loads(row["result"] or "null")
            except ValueError:
                result = None
            line = {"result": result, "error": row["error"]}
            say(f"  {GLYPH.get(row['status'], '?')} {row['step_id']:<3} {row['tool']:<22} {_detail(line)}")

    def _adopt(self) -> None:
        """Take the newest run we have not printed yet: the resumed run gets progress too, even
        though `checkpoint.resume` only reveals its run_id after it has already started."""
        if self.run_id is not None or self._conn is None:
            return
        try:
            row = self._conn.execute("SELECT run_id FROM runs ORDER BY rowid DESC LIMIT 1").fetchone()
        except sqlite3.Error:
            return
        if row is not None and row["run_id"] not in self.avoid:
            self.run_id = row["run_id"]

    def _loop(self) -> None:
        deadline = time.monotonic() + 120  # a hung run must not leave a thread printing forever
        while not self._stop.is_set() and time.monotonic() < deadline:
            if not self._connect():
                self._stop.wait(0.02)
                continue
            self._adopt()
            self._drain()
            if self.run_id is None:
                self._stop.wait(self.poll)
                continue
            try:
                row = self._conn.execute("SELECT status FROM runs WHERE run_id=?", (self.run_id,)).fetchone()
            except sqlite3.Error:
                row = None
            if row and row["status"] != "running":
                break
            self._stop.wait(self.poll)
        self._drain()

    def __enter__(self) -> "Follower":
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
        if self._connect():  # a run shorter than one poll still gets its step lines printed
            self._adopt()
            self._drain()
        if self._conn is not None:
            self._conn.close()


# ------------------------------------------------------------------- execution
def authorizer_for(queue: str | None, *, gate: bool = True) -> Callable[..., str] | None:
    """`hitl.authorizer` bound to our queue file, so the CLI gates the money path (HELP-5).

    `None` means no gate at all — every tool allowed. Only for read-only tasks.
    """
    if not gate:
        return None
    from src.reliability.hitl import authorizer  # noqa: PLC0415 - keeps the banner instant

    return functools.partial(authorizer, path=queue) if queue else authorizer


def execute(task: str, *, run_root: Path, run_id: str, offline: bool, queue: str | None,
            gate: bool, label: str) -> dict[str, Any]:
    """One pass of the frozen loop, with live step progress."""
    from src.runtime.loop import run_task  # noqa: PLC0415

    say(f"\n{label}  {run_id}")
    with Follower(run_root / LEDGER_NAME, run_id):
        return run_task(task, run_id=run_id, run_root=run_root, offline=offline,
                        authorizer=authorizer_for(queue, gate=gate))


def continue_run(run_root: Path, run_id: str, *, offline: bool, queue: str | None, gate: bool) -> dict[str, Any]:
    """Continue a blocked run under a new run_id (the ledger is append-only, so ids are not recycled).

    `checkpoint.resume` re-enters the same loop: what already succeeded replays from the
    idempotency index, so only the blocked step executes for real.
    """
    from src.reliability.checkpoint import resume as resume_run  # noqa: PLC0415

    say(f"\nrun 2  continuing {run_id}  (new run id: the ledger is append-only)")
    with Follower(run_root / LEDGER_NAME, avoid={run_id}):
        return resume_run(run_root, run_id, offline=offline, authorizer=authorizer_for(queue, gate=gate))


# ------------------------------------------------------------------ approvals
def _tools_of(out: dict[str, Any]) -> set[str]:
    """Tools this run actually tried. evidence.json is written before run_task returns, so this
    needs no new plumbing — and it is what scopes approvals: a queue shared with other runs (the
    repo's data/gate.jsonl holds every request ever made) is not this run's business."""
    try:
        steps = json.loads(Path(out["evidence"]).read_text(encoding="utf-8"))["steps"]
        return {str(s["tool"]) for s in steps}
    except (OSError, ValueError, KeyError, TypeError):
        return set()


def settle(queue: str | None, out: dict[str, Any], run_root: Path, task: str, *,
            approve: str | None) -> bool:
    """Close the requests *this run* raised, so it can continue. True when at least one was granted.

    `--approve WHO` signs off for a named human (the decision lands in the queue, so the audit
    trail says who); on a TTY without it, one y/N prompt per request — a "no" is recorded as a
    denial, not a shrug. Non-interactive without `--approve` prints the exact commands to run next
    instead of stalling: no dead ends.
    """
    from src.reliability import hitl  # noqa: PLC0415

    mine = set(_tools_of(out))
    pending = [r for r in hitl.pending(queue) if r.get("tool") in mine] if (queue and mine) else []
    if not pending:
        return False
    say(f"\n{len(pending)} approval{'s' if len(pending) > 1 else ''} needed before this can continue:")
    granted = False
    for rec in pending:
        rid, tool = rec["request_id"], rec["tool"]
        amount = f" {money(rec['amount'])}" if isinstance(rec.get("amount"), (int, float)) else ""
        why = rec.get("reason") or "policy requires a human"
        if approve is not None:
            name = approve or approver_name()
            hitl.decide(rid, approver=name, path=queue)
            say(f"  ✓ {rid}  {tool}{amount}  approved by {name}   ({why})")
            granted = True
        elif sys.stdin.isatty():
            name = approver_name()
            if input(f"  approve {rid} {tool}{amount} ({why})? [y/N] ").strip().lower() in ("y", "yes"):
                hitl.decide(rid, approver=name, path=queue)
                say(f"  ✓ {rid}  approved by {name}")
                granted = True
            else:
                hitl.decide(rid, approver=name, approve=False, reason="denied at the prompt", path=queue)
                say(f"  ✗ {rid}  denied by {name}   (recorded; it stays denied until someone "
                    f"queues a new request)")
        else:
            say(f"  ⏸ {rid}  {tool}{amount}  waiting for a human   ({why})")
            say(f"      next: python3 -m src.reliability.hitl --approve {rid} --approver <you>")
            say(f'      then: python3 -m src.cli.main run --task "{task}" --runs {run_root} --approve <you>')
    return granted


def report(out: dict[str, Any], *, extra: list[str] | None = None, next_hint: str = "") -> int:
    """Print the verdict line an evaluator reads first, plus every predicate that failed."""
    verdict = out.get("verdict") or {}
    predicates = verdict.get("predicates") or []
    passed = sum(1 for p in predicates if p.get("passed"))
    total = len(predicates)
    status = verdict.get("status", "blocked")
    replayed = sum(1 for s in out.get("steps") or [] if s == "cached")
    if status == "pass":
        line = f"verdict: pass {passed}/{total}"
    elif status == "blocked":
        line = f"verdict: blocked / {verdict.get('summary') or 'waiting on a human'}"
    else:
        line = f"verdict: fail {passed}/{total}"
    say(f"\n{line}   replayed={replayed}   plan: {out.get('plan_source')}   run: {out.get('run_id')}")
    for pred in predicates:
        if not pred.get("passed") and pred.get("weight", 1):
            say(f"  ✗ {pred['name']}: {pred.get('detail') or pred['statement']}")
    for note in extra or []:
        say(note)
    say(f"evidence: {out.get('evidence')}")
    if next_hint:
        say(f"next: {next_hint}")
    return 0 if out.get("status") == "completed" else 1


# --------------------------------------------------------------------- shared
def drive(task: str, *, run_root: Path, queue: str | None, offline: bool, gate: bool,
          approve: str | None, next_hint: str = "",
          extra: Callable[[dict[str, Any]], list[str]] | None = None) -> tuple[dict[str, Any], int]:
    """Run a task through the gate: execute, and if a human is the only thing in the way, sign off
    and continue once. That continuation is the whole demo: blocked run -> approval -> verified post.

    Returns (final run summary, exit code).
    """
    from src.ledger.store import new_run_id  # noqa: PLC0415

    head("task", task or "(empty)")
    out = execute(task, run_root=run_root, run_id=new_run_id(), offline=offline,
                  queue=queue, gate=gate, label="run 1")
    if out["status"] == "blocked" and settle(queue, out, run_root, task, approve=approve):
        out = continue_run(run_root, out["run_id"], offline=offline, queue=queue, gate=gate)
    return out, report(out, extra=extra(out) if extra else [], next_hint=next_hint)


def seed_ok() -> tuple[bool, str]:
    """The demo's input data ships with the repo; if it is gone, say how to get it back."""
    from src.tools.invoice_tool import find_latest  # noqa: PLC0415

    files = sorted((ROOT / "data" / "seed" / "invoices").glob("*"))
    if not files:
        return False, "no seed invoices — next: python3 data/seed/make_pdfs.py"
    probe = find_latest("Company X")
    latest = probe.get("latest") or {}
    if not latest:
        return False, f"no parseable Company X invoice — next: python3 data/seed/make_pdfs.py ({probe.get('error')})"
    return True, (f"{len(files)} files in data/seed/invoices, newest = {latest['invoice_number']}"
                  f" {money(latest['amount'])} due {latest['due']}")


SCRATCH_ROOTS = tuple(p.rstrip("/") for p in ("/tmp", os.environ.get("TMPDIR", "")) if p)


def _is_scratch(path: Path) -> bool:
    """Is this a scratch path we may delete? Compared textually, never through `resolve()`:
    on macOS /tmp is a symlink to /private/tmp, which would make every check fail."""
    target = os.path.abspath(path)
    return any(target == root or target.startswith(root + "/") for root in SCRATCH_ROOTS)


def fresh(path: Path, *, keep: bool, what: str) -> None:
    """Wipe a scratch path so the demo is reproducible (B1-F2: a dirty DB made runs unreadable).

    This is the only destructive thing the CLI does, it says so first, and it refuses to delete
    anything outside the scratch roots — an explicit `--append` is how a caller keeps state.
    """
    if keep:
        head("kept", f"{path}  (kept, as asked)")
        return
    if path.exists() and not _is_scratch(path):
        head("kept", f"{path}  (not a scratch path, never deleted here)")
        return
    existed = path.exists()
    if existed:
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
    head("reset" if existed else "fresh", f"{path}  ({what})")
    if existed:
        say("             scratch only — undo = recreate with: bash demo/run.sh")


# ----------------------------------------------------------------------- demo
def cmd_demo(args: argparse.Namespace) -> int:
    """One command, start to finish: sim ERP, seeded invoice, approval, verified post, evidence."""
    runs = Path(args.runs or SCRATCH / "runs")
    root = runs.parent  # the queue and the ERP db sit beside the run root, not somewhere else
    queue = args.queue or str(root / "gate.jsonl")
    db = Path(args.db or root / "sim.db")
    keep = bool(args.append)

    ok, detail = seed_ok()
    head("seed", detail)
    if not ok:
        return 1

    sim: subprocess.Popen | None = None
    try:
        if args.erp_url:
            base = args.erp_url.rstrip("/")
            if health(base) is None:
                say(f"sim ERP   {base} is not answering — next: python3 sim_app/server.py "
                    f"--port {free_port()} --db {db}")
                return 1
            head("sim ERP", f"{base}  (already running, left alone)")
        else:
            fresh(db, keep=keep, what="empty ERP db")
            port = args.port or free_port()
            base = f"http://127.0.0.1:{port}"
            sim = start_sim(db, port)
            if not wait_sim(base, db, sim):
                other = health(base)
                if other is not None and str(other.get("db")) != str(db):
                    say(f"sim ERP   port {port} already serves another ERP (db={other.get('db')}) — "
                        f"next: drop --port {port}, or pass a free one")
                else:
                    say(f"sim ERP   did not come up at {base} — next: python3 sim_app/server.py "
                        f"--port {port} --db {db}")
                return 1
            head("sim ERP", f"{base}  db={db}  (started for this run, stopped when it ends)")
        os.environ["ERP_URL"] = base  # the tool reads $ERP_URL; the planner leaves base_url empty

        fresh(runs, keep=keep, what="run root")
        fresh(Path(queue), keep=keep, what="approval queue")
        before = erp_count(base)
        head("erp rows", "unreachable" if before is None else str(before))

        def rows_line(out: dict[str, Any]) -> list[str]:
            after = erp_count(base)
            if after is None:
                return []
            unchanged = "  (unchanged: nothing was double-posted)" if after == before else ""
            return [f"ERP count: {after}{unchanged}"]

        out, rc = drive(DEFAULT_TASK, run_root=runs, queue=queue, offline=not args.llm,
                        gate=not args.no_gate, approve=args.approve, extra=rows_line,
                        next_hint=("python3 -m src.cli.main demo   # again without --append: a cold run"
                                   if keep else
                                   "bash demo/run.sh --append   # same scratch, same task: watch replayed=2"))
        if args.json:
            say(json.dumps({"demo": "invoice intake", "erp": base, "rows": erp_count(base),
                            "run": out.get("run_id"), "verdict": (out.get("verdict") or {}).get("status")},
                           indent=2))
        return rc
    finally:
        if sim is not None:
            sim.terminate()
            try:
                sim.wait(timeout=5)
            except subprocess.TimeoutExpired:  # pragma: no cover - only on a wedged server
                sim.kill()


# ------------------------------------------------------------------------ run
def cmd_run(args: argparse.Namespace) -> int:
    """Any task through the loop, with the approval gate wired and the evidence path printed."""
    from src.reliability.hitl import queue_path  # noqa: PLC0415

    runs = Path(args.runs or ROOT / "runs")
    task = args.task
    # An empty ask is the one verdict that is blocked before a plan exists, so there is no audit
    # value in a run dir for it: with the repo default implied, keep the tree clean and scratch instead.
    if args.runs is None and not task.strip():
        runs = SCRATCH / "runs"
        head("runs", f"{runs}  (empty ask: nothing to audit, so not under the repo's runs/)")
    queue = args.queue or str(queue_path())
    # No key means the LLM path can only fail, so plan heuristically and skip the pointless call.
    offline = args.offline or not os.environ.get("OPENAI_API_KEY")
    hint = ("python3 -m src.cli.main demo   # the whole thing, one command, offline"
            if not task.strip() else
            f'python3 -m src.cli.main run --task "{task}" --runs {runs}   # replays, never re-posts')
    out, rc = drive(task, run_root=runs, queue=queue, offline=offline, gate=not args.no_gate,
                    approve=args.approve, next_hint=hint)
    if args.json:
        say(json.dumps(out, indent=2, default=str))
    return rc


# --------------------------------------------------------------------- doctor
def cmd_doctor(args: argparse.Namespace) -> int:
    from src.cli.doctor import main as doctor_main  # noqa: PLC0415 - keeps the banner instant

    return doctor_main(["--browser"] if args.browser else [])


# --------------------------------------------------------------------- parser
def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="python3 -m src.cli.main", description="Run one CentrAlign task, or the whole demo.",
        epilog=f'try:  python3 -m src.cli.main demo\n      python3 -m src.cli.main run --task "{DEFAULT_TASK}"',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = ap.add_subparsers(dest="command")

    demo = sub.add_parser("demo", help="the invoice-intake demo end to end, offline, one command")
    demo.add_argument("--runs", default=None, help=f"run root dir (default: {SCRATCH / 'runs'})")
    demo.add_argument("--db", default=None, help=f"scratch sim ERP db (default: {SCRATCH / 'sim.db'})")
    demo.add_argument("--queue", default=None, help="approval queue file (default: <scratch>/gate.jsonl)")
    demo.add_argument("--erp-url", default=None, help="use a sim ERP that is already running")
    demo.add_argument("--port", type=int, default=0, help="port for the sim ERP this demo starts (default: free)")
    demo.add_argument("--append", action="store_true",
                      help="keep the runs dir and the ERP db: the second run replays instead of re-posting")
    demo.add_argument("--approve", nargs="?", const="", metavar="WHO",
                      help="sign off on the approval as WHO (non-interactive demo/CI)")
    demo.add_argument("--no-gate", action="store_true", help="skip the approval gate (shows what it protects)")
    demo.add_argument("--llm", action="store_true", help="plan with the LLM if OPENAI_API_KEY is set")
    demo.add_argument("--json", action="store_true", help="print a machine-readable summary too")
    demo.set_defaults(func=cmd_demo)

    run = sub.add_parser("run", help="run one task end to end")
    run.add_argument("--task", required=True, help=f'the ask, e.g. "{DEFAULT_TASK}"')
    run.add_argument("--runs", default=None, help="run root dir (default: runs/)")
    run.add_argument("--queue", default=None,
                     help="approval queue file (default: data/gate.jsonl, from company.yaml approval.queue)")
    run.add_argument("--approve", nargs="?", const="", metavar="WHO",
                     help="sign off on the approvals this run needs, as WHO")
    run.add_argument("--offline", action="store_true", help="never call the LLM planner (default: heuristic anyway)")
    run.add_argument("--no-gate", action="store_true", help="skip the approval gate (read-only tasks)")
    run.add_argument("--json", action="store_true", help="print the run summary as JSON")
    run.set_defaults(func=cmd_run)

    doc = sub.add_parser("doctor", help="is this machine ready? (exit 0 = yes, offline included)")
    doc.add_argument("--browser", action="store_true", help="also require the optional Playwright browser path")
    doc.set_defaults(func=cmd_doctor)
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    say(BANNER)  # before anything heavy: this line is the <1s promise
    if not getattr(args, "command", None):
        build_parser().print_help()
        return 0
    try:
        return int(args.func(args))
    except KeyboardInterrupt:  # a run is durable: the ledger knows how far it got
        say("\ninterrupted — nothing is lost; continue with: "
            "python3 -m src.reliability.checkpoint --runs <runs> --resume <run_id>")
        return 130
    except Exception as exc:  # noqa: BLE001 - a CLI shows the error, the traceback goes to stderr
        say(f"\n{type(exc).__name__}: {exc}")
        say("next: python3 -m src.cli.main doctor   (does this machine have what the run needs?)")
        traceback.print_exc(file=sys.stderr)
        return 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BrokenPipeError:  # `demo | head` closes the pipe; that is the reader's choice, not a failure
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        raise SystemExit(0) from None
