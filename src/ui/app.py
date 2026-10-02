"""Evaluator-visible demo UI: stdlib `http.server` + one HTML page. No new dependencies.

    python3 -m src.ui.app                 # scratch sim ERP + scratch ledger, prints the URL
    python3 -m src.ui.app --port 0        # same, on an OS-picked free port

One page: what this is + the 8-stage loop → pick a job → Run → live steps (read out of the
ledger, polled) → Approve → verdict + evidence + the ERP row, with the plan and the name of the
planner that wrote it on screen the whole time. Nothing here re-implements the demo: `src.cli.main`
owns the sim ERP lifecycle and the row count, `run_task` / `checkpoint.resume` do the work, and
`hitl.decide` is the only way a request closes. Binds 127.0.0.1, needs no browser — the test drives
the same HTTP. It plans online: `GEMINI_API_KEY` (or `OPENAI_API_KEY`) in the environment and the
model writes the plan, and the page says which one did. Unkeyed, the run still finishes and the
badge names the reason it fell back to the deterministic planner.
"""

from __future__ import annotations

import argparse
import functools
import json
import os
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from src.cli import main as cli
from src.contracts.events import redact
from src.ledger.evidence import load_evidence
from src.ledger.store import Ledger, new_run_id
from src.reliability import hitl
from src.reliability.checkpoint import resume as resume_run
from src.runtime.loop import run_task
from src.tools import erp_tool

PAGE = Path(__file__).with_name("index.html")
LEDGER_NAME = "_ledger.sqlite3"
SCRATCH = Path(os.environ.get("CENTRALIGN_UI_SCRATCH", "/tmp/centralign-ui"))
PHASE_TEXT = {
    "idle": "press Run",
    "running": "working…",
    "awaiting": "waiting for a human",
    "done": "done",
}
# The loop's own vocabulary, in order: `src.runtime.loop` docstring, same eight names.
STAGES = ("goal", "understand", "plan", "execute", "observe", "adapt", "verify", "complete")
# The jobs on the gallery. Each card says the tool chain in plain words *before* you click, so what
# the page does next is never a surprise, and `gate` says up front whether a human is needed.
SCENARIOS: list[dict[str, str]] = [
    {
        "id": "intake",
        "title": "Post the latest invoice",
        "task": cli.DEFAULT_TASK,
        "chain": "find the latest invoice for Company X → post it to the ERP",
        "gate": "one approval: the ERP post",
    },
    {
        "id": "inbox",
        "title": "Summarize the invoice inbox",
        "task": "list the invoice inbox in seed/invoices and parse INV-X-2024-0703-acme.pdf "
                "and INV-Y-2024-0805-other.txt",
        "chain": "list seed/invoices → parse the two files it names → report the inbox",
        "gate": "read-only: no approval, nothing posted",
    },
    {
        "id": "check",
        "title": "Check the latest invoice, post nothing",
        "task": "find the latest invoice for Company X and report its vendor, amount and due date",
        "chain": "find the latest invoice for Company X → report it, write nothing",
        "gate": "read-only: no approval, nothing posted",
    },
]


def stages_of(run: dict[str, Any], events: list[dict[str, Any]]) -> list[str]:
    """The stages this run entered, in order, from the events the run wrote itself.

    `run.started` lands before Understand and `step.planned` after Plan, so those two mark that
    stretch; every other stage event names itself outright. A run that ended `blocked` — waiting on
    a human — has not completed, so the strip stays on the stage it really reached instead of
    lighting Complete while a decision is still outstanding. Nothing here is timed or guessed: a
    run that outruns the 500ms poll simply arrives with its whole trail already written.
    """
    reached: list[str] = []

    def mark(name: str) -> None:
        if name in STAGES and name not in reached:
            reached.append(name)

    for ev in events:
        kind = ev.get("type")
        if kind == "run.started":
            mark("goal")
            mark("understand")
        elif kind == "step.planned":
            mark("plan")
        elif kind == "run.stage":
            mark(str((ev.get("payload") or {}).get("stage") or ""))
        elif kind == "verify.checked":
            mark("verify")
        elif kind in ("run.completed", "run.failed") and str(run.get("status")) == "completed":
            mark("complete")
    return reached


class Busy(RuntimeError):
    """The page asked for something the run in flight cannot do yet."""


# ------------------------------------------------------------------ step rows
def latest_per_step(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One row per step. The ledger is append-only, so a retry adds a row rather than editing one."""
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        out[row["step_id"]] = row
    return sorted(out.values(), key=lambda r: (int(r.get("seq") or 0), int(r.get("attempt") or 0)))


def detail(row: dict[str, Any]) -> str:
    """One honest line per step: what the tool actually returned, or why it did not run."""
    error = str(row.get("error") or "")
    if error:
        # The frozen executor words the gate "no approval channel in Phase 01". On this page that is
        # false — the queue is in the card beside it. The raw text stays in evidence.json.
        if error.startswith("blocked: approval required"):
            return "not posted — waiting for a human to approve it (the card beside this list)"
        return error
    res = row.get("result") if isinstance(row.get("result"), dict) else {}
    latest = res.get("latest")
    if isinstance(latest, dict):
        return (f"{latest.get('invoice_number')}  {cli.money(latest.get('amount'))} {latest.get('currency')}"
                f"  due {latest.get('due')}")
    # A read-side scenario earns its keep by saying what it read, so name the files and the totals.
    files = res.get("files")
    if isinstance(files, list):
        return f"{res.get('count', len(files))} files in {res.get('dir')} · " + ", ".join(
            str(f.get("name")) for f in files if isinstance(f, dict))
    if res.get("invoice_number"):
        return (f"{res.get('invoice_number')}  {cli.money(res.get('amount'))} {res.get('currency')}"
                f"  due {res.get('due')}  ({res.get('vendor')})")
    body = res.get("body")
    if isinstance(body, dict) and body.get("id"):
        return f"ERP row #{body['id']} " + ("created" if body.get("created") else "already posted (idempotent)")
    return ""


def banner(verdict: dict[str, Any] | None, replayed: int) -> str:
    """The one line an evaluator reads, worded exactly like the CLI's `report()`."""
    verdict = verdict or {}
    preds = verdict.get("predicates") or []
    passed, total = sum(1 for p in preds if p.get("passed")), len(preds)
    status = verdict.get("status", "blocked")
    if status == "pass":
        return f"pass {passed}/{total}"
    if status == "blocked":
        return f"blocked / {verdict.get('summary') or 'waiting on a human'}"
    return f"fail {passed}/{total}"


# -------------------------------------------------------------------- session
class Demo:
    """The invoice demo the page drives: run → approval → verified post → evidence.

    One cycle is exactly what `src.cli.main demo` does — run, then (if a human is the only thing in
    the way) approve and continue once — with the blocking part left to the page's Approve button.

    The page plans **online**: `offline=False` means `make_plan` asks the model and the run records
    which one answered (`llm:gemini/<model>`), or the reason it could not. There is no offline mode
    on this page — `offline=True` is not a switch an operator can flip, it is what the tests pass so
    the no-key path stays covered without a socket.
    """

    def __init__(self, *, scratch: Path | str = SCRATCH, task: str | None = None,
                 erp_url: str | None = None, offline: bool = False) -> None:
        self.scratch = Path(scratch)
        self.task = task or cli.DEFAULT_TASK
        self.offline = offline
        self.run_root = self.scratch / "runs"
        self.queue = str(self.scratch / "gate.jsonl")
        self.db = self.scratch / "sim.db"
        self.sim: subprocess.Popen | None = None
        self._lock = threading.Lock()
        self.phase, self.clicks, self.display, self.blocked = "idle", 0, None, None
        self.pending: list[dict[str, Any]] = []
        self.error: str | None = None
        # A custom --task belongs to no card, so the gallery shows nothing selected rather than lying.
        self.scenario = next((s for s in SCENARIOS if s["task"] == self.task), None)
        self._cold()
        self.erp_url = erp_url or self._start_erp()
        os.environ["ERP_URL"] = self.erp_url  # the tool reads $ERP_URL; the planner leaves base_url empty

    def _cold(self) -> None:
        """Wipe the scratch. A leftover ERP row or a warm ledger is what made the CLI demo
        unreadable, and a grant from an earlier session would skip the approval card entirely."""
        cli.fresh(self.db, keep=False, what="empty ERP db")
        cli.fresh(self.run_root, keep=False, what="run root")
        cli.fresh(Path(self.queue), keep=False, what="approval queue")

    # ---- sim ERP ---------------------------------------------------------
    def _start_erp(self) -> str:
        port = cli.free_port()
        base = f"http://127.0.0.1:{port}"
        self.sim = cli.start_sim(self.db, port)
        if not cli.wait_sim(base, self.db, self.sim):
            raise RuntimeError(f"the sim ERP did not come up at {base}; start it yourself: "
                               f"python3 sim_app/server.py --port {cli.free_port()} --db {self.db}")
        cli.head("sim ERP", f"{base}  db={self.db}  (started for this page, stopped with it)")
        return base

    def close(self) -> None:
        if self.sim is not None:
            self.sim.terminate()
            try:
                self.sim.wait(timeout=5)
            except subprocess.TimeoutExpired:  # pragma: no cover - only on a wedged server
                self.sim.kill()
            self.sim = None

    # ---- one click of a card, one click of Run ----------------------------
    def select(self, scenario_id: str) -> dict[str, Any]:
        """Load a job's task and wipe the page back to cold, so the next Run really is a first run.

        Cold on purpose: a warm ledger would replay the previous job's steps into this one's steps
        list and leave its ERP row on screen where the new one starts.
        """
        scenario = next((s for s in SCENARIOS if s["id"] == scenario_id), None)
        if scenario is None:
            raise KeyError(scenario_id)
        with self._lock:
            if self.phase in ("running", "awaiting"):
                raise Busy(f"a run is already in flight ({PHASE_TEXT[self.phase]})")
            self.scenario, self.task = scenario, scenario["task"]
            self._cold()
            self.phase, self.clicks, self.display, self.blocked = "idle", 0, None, None
            self.pending, self.error = [], None
        return self.state()

    def start(self) -> dict[str, Any]:
        """Kick off a cycle in the background; the page polls for what it did."""
        with self._lock:
            if self.phase in ("running", "awaiting"):
                raise Busy(f"a run is already in flight ({PHASE_TEXT[self.phase]})")
            self.clicks, self.error = self.clicks + 1, None
            self.phase, self.display, self.blocked, self.pending = "running", None, None, []
        threading.Thread(target=self._cycle, daemon=True).start()
        return self.state()

    def approve(self, request_id: str, approver: str = "") -> dict[str, Any]:
        """Close one named request, then continue the blocked run once nothing of ours is open.

        Deny by default, exactly as the CLI is: `hitl.decide` refuses an unknown or already-closed
        id, so the button can only ever release the request the card names.
        """
        with self._lock:
            if self.phase != "awaiting":
                raise Busy("nothing is waiting for a human right now")
            waiting = self.blocked
        rec = hitl.decide(request_id, approver=(approver or "").strip() or cli.approver_name(), path=self.queue)
        with self._lock:
            self.pending = self._pending_for(waiting) if waiting else []
            if self.pending:
                return {"approved": rec, **self.state()}
            self.phase = "running"
        threading.Thread(target=self._continue, args=(waiting,), daemon=True).start()
        return {"approved": rec, **self.state()}

    # ---- the two worker paths (one thread each) ---------------------------
    def _cycle(self) -> None:
        try:
            out = run_task(self.task, run_id=new_run_id(), run_root=self.run_root,
                           offline=self.offline,  # False: the model plans, and the run records its name
                           authorizer=functools.partial(hitl.authorizer, path=self.queue))
            self._note(out)
            if self._await(out["run_id"]):
                return
            self._done()
        except Exception as exc:  # noqa: BLE001 - the page shows the error instead of going blank
            self._fail(exc)

    def _continue(self, run_id: str) -> None:
        try:
            out = resume_run(self.run_root, run_id, offline=self.offline,
                            authorizer=functools.partial(hitl.authorizer, path=self.queue))
            self._note(out)
            self._done()
        except Exception as exc:  # noqa: BLE001
            self._fail(exc)

    def _pending_for(self, run_id: str) -> list[dict[str, Any]]:
        """This run's open requests only: a shared queue file holds every request ever made."""
        with Ledger(self.run_root / LEDGER_NAME, run_root=self.run_root) as led:
            mine = {str(row["tool"]) for row in led.steps_for_run(run_id)}
        return [r for r in hitl.pending(self.queue) if r.get("tool") in mine]

    def _note(self, out: dict[str, Any]) -> None:
        with self._lock:
            self.display, self.blocked = out["run_id"], out["run_id"]

    def _await(self, run_id: str) -> bool:
        """True when the page has a decision to make; also flips the phase to `awaiting`."""
        with self._lock:
            pending = self._pending_for(run_id)
            if not pending:
                return False
            self.pending = pending
            self.phase = "awaiting"
            return True

    def _done(self) -> None:
        with self._lock:
            self.phase, self.error = "done", None

    def _fail(self, exc: Exception) -> None:
        with self._lock:
            self.phase, self.error = "done", f"{type(exc).__name__}: {exc}"

    # ---- what the page renders ------------------------------------------
    def state(self) -> dict[str, Any]:
        """Everything on screen, read fresh: the ledger for steps and verdict, the ERP for the row."""
        with self._lock:
            out: dict[str, Any] = {
                "task": self.task, "phase": self.phase, "phase_text": PHASE_TEXT[self.phase],
                "clicks": self.clicks, "run_id": self.display, "blocked_run": self.blocked,
                "pending": list(self.pending), "error": self.error, "erp_url": self.erp_url,
                "scratch": str(self.scratch), "steps": [], "verdict": None, "banner": "",
                "evidence": None, "evidence_path": None, "erp": None, "done": False,
                "scenario": (self.scenario or {}).get("id"), "scenarios": SCENARIOS,
                "stages": [], "plan": None, "plan_source": "",
            }
            run_id = self.display
        if not run_id:
            return redact(out)
        with Ledger(self.run_root / LEDGER_NAME, run_root=self.run_root) as led:
            run = led.get_run(run_id) or {}
            rows = latest_per_step(led.steps_for_run(run_id))
            events = led.events_for_run(run_id)
        out["steps"] = [{**{k: row.get(k) for k in ("seq", "step_id", "tool", "status", "attempt")},
                         "detail": detail(row)} for row in rows]
        out["verdict"] = json.loads(run["verdict"]) if run.get("verdict") else None
        out["banner"] = banner(out["verdict"], replayed=sum(1 for r in rows if r["status"] == "cached"))
        out["erp"] = self._erp()
        out["done"] = str(run.get("status")) in ("completed", "failed", "blocked")
        out["stages"] = stages_of(run, events)
        if out["done"]:  # evidence.json is written once, at the end of a run
            run_dir = self.run_root / run_id
            if (run_dir / "evidence.json").is_file():
                out["evidence"], out["evidence_path"] = load_evidence(run_dir), str(run_dir / "evidence.json")
        # The plan and who wrote it, read live out of the run's own state.json, so the AI panel
        # fills in while the run works. Once the bundle exists the same value is read from
        # `evidence.run.plan_source` — one field, never a label of our own choosing.
        snap = self._snapshot(run_id)
        out["plan"] = snap.get("plan") or (out["evidence"] or {}).get("plan")
        out["plan_source"] = ((out["evidence"] or {}).get("run") or {}).get("plan_source") \
            or str(snap.get("plan_source") or "")
        return redact(out)

    def _snapshot(self, run_id: str) -> dict[str, Any]:
        """The run's last `state.json`, or `{}` — the loop rewrites it at every stage boundary."""
        try:
            data = json.loads((self.run_root / run_id / "state.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):  # not written yet, or a truncated write: the page just waits
            return {}
        return data if isinstance(data, dict) else {}

    def _erp(self) -> dict[str, Any] | None:
        res = erp_tool.list_invoices(base=self.erp_url)
        body = res.get("body") if res.get("ok") else None
        rows = (body or {}).get("invoices") or []
        return {"count": (body or {}).get("count", 0), "row": rows[0] if rows else None}


# ---------------------------------------------------------------- http layer
class Handler(BaseHTTPRequestHandler):
    server_version = "CentrAlignUI/1.0"

    def _send(self, code: int, payload: Any, ctype: str = "application/json") -> None:
        body = payload.encode() if isinstance(payload, str) else json.dumps(payload, default=str).encode()
        self.send_response(code)
        self.send_header("Content-Type", f"{ctype}; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _payload(self) -> dict[str, Any]:
        """The JSON body, or `{}`. Anything that is not an object is refused rather than trusted:
        the page is the only client, but it is still the network edge."""
        try:
            data = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        except ValueError:
            return {}
        return data if isinstance(data, dict) else {}

    def do_GET(self) -> None:  # noqa: N802 - http.server's name
        path = urlparse(self.path).path.rstrip("/") or "/"
        if path == "/":
            return self._send(200, PAGE.read_text(encoding="utf-8"), "text/html; charset=utf-8")
        if path == "/api/state":
            return self._send(200, self.server.demo.state())  # type: ignore[attr-defined]
        self._send(404, {"error": "no such route", "path": path})

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path.rstrip("/") or "/"
        body = self._payload()
        try:
            if path == "/api/run":
                self._send(202, self.server.demo.start())  # type: ignore[attr-defined]
            elif path == "/api/scenario":
                self._send(200, self.server.demo.select(str(body.get("id") or "")))  # type: ignore[attr-defined]
            elif path == "/api/approve":
                self._send(200, self.server.demo.approve(  # type: ignore[attr-defined]
                    str(body.get("request_id") or ""), str(body.get("approver") or "")))
            else:
                self._send(404, {"error": "no such route", "path": path})
        except Busy as exc:
            self._send(409, {"error": str(exc)})
        except KeyError as exc:
            self._send(404, {"error": f"no such scenario: {exc.args[0]!r}",
                             "known": [s["id"] for s in SCENARIOS]})
        except hitl.ApprovalError as exc:
            self._send(409, {"error": f"refused: {exc}"})

    def log_message(self, *args: Any) -> None:
        """Silent: the page polls twice a second and a log line per poll is noise, not a trail.
        The ledger is the audit trail."""


def serve(demo: Demo, *, host: str = "127.0.0.1", port: int = 0) -> ThreadingHTTPServer:
    """Bind the page. Localhost only — it approves money, so it is never routable."""
    server = ThreadingHTTPServer((host, port), Handler)
    server.demo = demo  # type: ignore[attr-defined]
    return server


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python3 -m src.ui.app", description=__doc__.splitlines()[0])
    ap.add_argument("--port", type=int, default=0, help="0 = an OS-picked free port (default)")
    ap.add_argument("--host", default="127.0.0.1", help="localhost only; anything routable is refused")
    ap.add_argument("--scratch", default=str(SCRATCH), help=f"scratch dir (default: {SCRATCH})")
    ap.add_argument("--task", default=cli.DEFAULT_TASK, help="the ask the Run button sends")
    ap.add_argument("--erp-url", default=None, help="use a sim ERP that is already running")
    args = ap.parse_args(argv)
    if args.host != "127.0.0.1":
        ap.error("this page is localhost-only; --host must be 127.0.0.1")

    demo = Demo(scratch=Path(args.scratch), task=args.task, erp_url=args.erp_url)
    server = serve(demo, host=args.host, port=args.port)
    cli.say(f"\nCentrAlign demo UI  http://{args.host}:{server.server_address[1]}")
    cli.say(f"task    {demo.task}")
    cli.say("planner online — the page names the model that planned the run, or why it could not")
    cli.say(f"scratch {demo.scratch}  (wiped on start; rerun for a cold pass 8/8)")
    cli.say("ctrl-c stops the page and the sim ERP\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        cli.say("\nstopped")
    finally:
        server.server_close()
        demo.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())