"""Phase 05 demo, offline: the exact commands from prompts/phase-05-demo-ux/BUILD.md, no API key.

The demo is driven end to end against a scratch sim ERP (empty db) and a scratch runs dir, so the
numbers the BUILD asserts are the numbers this file asserts: 8/8 cold, `replayed=2` warm,
`blocked / No task given` for an empty ask, doctor green offline, and the ERP post gated until a
human signs off. No network, no browser, no API key.
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.cli import doctor, main as cli  # noqa: E402
from src.reliability import hitl  # noqa: E402


@pytest.fixture
def sim(tmp_path: Path):
    """A sim ERP on an OS-picked port with an empty db.

    B1-F2: `data/sim_erp.db` persists between sessions, which made the demo's first POST
    indistinguishable from a replay. The demo (and this fixture) start from nothing.
    """
    from sim_app.server import make_server

    server = make_server("127.0.0.1", 0, tmp_path / "sim.db")
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    os.environ["ERP_URL"] = base
    try:
        yield base
    finally:
        os.environ.pop("ERP_URL", None)
        server.shutdown()
        server.server_close()


def demo_args(sim: str, tmp_path: Path, *extra: str) -> list[str]:
    return ["demo", "--erp-url", sim, "--runs", str(tmp_path / "runs"),
            "--queue", str(tmp_path / "gate.jsonl"), "--approve", "tester", *extra]


def run_args(tmp_path: Path, task: str, *extra: str) -> list[str]:
    return ["run", "--task", task, "--runs", str(tmp_path / "runs"),
            "--queue", str(tmp_path / "gate.jsonl"), "--offline", *extra]


# ------------------------------------------------------------------------ demo
def test_cold_demo_passes_8_of_8_and_posts_exactly_one_row(sim: str, tmp_path: Path, capsys) -> None:
    assert cli.main(demo_args(sim, tmp_path)) == 0
    out = capsys.readouterr().out

    assert "verdict: pass 8/8" in out, out
    assert "ERP count: 1" in out, "a second row would mean the demo double-posted"
    assert "replayed=1" in out, "run 2 replays the find; run 1 must be the one that executed it"
    assert "plan: heuristic" in out, "no API key means the deterministic planner, stated plainly"

    # the money path went through a human, and the audit trail says who
    queue = str(tmp_path / "gate.jsonl")
    closed = [r for r in hitl.read(queue) if r.get("queue") == hitl.CLOSED]
    assert [r["approver"] for r in closed] == ["tester"], closed
    assert closed[0]["tool"] == "erp_post_invoice" and closed[0]["verdict"] == hitl.GRANTED

    # and the evidence bundles say what each run really did, in ledger order
    with sqlite3.connect(str(tmp_path / "runs" / "_ledger.sqlite3")) as conn:
        dirs = [row[0] for row in conn.execute("SELECT evidence_dir FROM runs ORDER BY rowid")]
    bundles = [json.loads((Path(d) / "evidence.json").read_text(encoding="utf-8")) for d in dirs]

    assert [b["totals"]["tools_actually_executed"] for b in bundles] == [
        ["invoice_find_latest"], ["erp_post_invoice"],
    ], "run 1 reads then blocks on the gate; run 2 replays the read and posts for real"
    assert bundles[-1]["verdict"]["status"] == "pass"
    assert bundles[-1]["totals"]["cached"] == 1 and bundles[-1]["totals"]["tools_replayed"] == [
        "invoice_find_latest"]


def test_warm_demo_replays_both_steps_and_posts_nothing_new(sim: str, tmp_path: Path, capsys) -> None:
    assert cli.main(demo_args(sim, tmp_path)) == 0
    capsys.readouterr()

    assert cli.main(demo_args(sim, tmp_path, "--append")) == 0, "--append keeps the ledger and the ERP db"
    out = capsys.readouterr().out

    assert "replayed=2" in out, out
    assert "verdict: pass 8/8" in out
    assert "ERP count: 1  (unchanged" in out, "a replay must not create a second ERP row"
    assert "approved by" not in out, "a warm run has nothing left to approve: both steps replay"


def test_the_demo_refuses_to_post_when_nobody_approves(sim: str, tmp_path: Path, capsys) -> None:
    """Same task, no `--approve`, no TTY: the run stops on the gate and names the next command."""
    assert cli.main(run_args(tmp_path, cli.DEFAULT_TASK)) == 1
    out = capsys.readouterr().out

    assert "waiting for a human" in out and "--approve" in out, out
    assert "verdict: blocked" in out
    pending = hitl.pending(str(tmp_path / "gate.jsonl"))
    assert [r["tool"] for r in pending] == ["erp_post_invoice"]
    assert cli.erp_count(sim) == 0, "a queued request must never reach the money path"


# ------------------------------------------------------------------------ edges
def test_empty_task_is_blocked_in_plain_words(tmp_path: Path, capsys) -> None:
    assert cli.main(run_args(tmp_path, "")) == 1
    out = capsys.readouterr().out
    assert "blocked / No task given" in out, out
    assert "src.cli.main demo" in out, "a dead end must not stay a dead end"


def test_an_empty_ask_does_not_litter_the_repo_runs_dir(capsys) -> None:
    """F3: a rejected ask is blocked before any plan, so its run dir has no audit value. With the
    repo default implied, it goes to scratch instead of dropping `runs/<id>/` into the tree."""
    repo_runs = cli.ROOT / "runs"

    def listing() -> set[Path]:
        return set(repo_runs.iterdir()) if repo_runs.is_dir() else set()

    before = listing()
    assert cli.main(["run", "--task", "", "--offline"]) == 1
    assert listing() == before, "an empty ask must not add a run dir under the repo's runs/"
    out = capsys.readouterr().out
    assert "blocked / No task given" in out, out
    assert str(cli.SCRATCH) in out, "the run moved to scratch and printed where it went"


def test_doctor_is_green_offline(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.delenv("ERP_URL", raising=False)
    monkeypatch.setenv("CENTRALIGN_RUNS", str(tmp_path / "runs"))
    assert doctor.main([]) == 0
    out = capsys.readouterr().out
    assert "not running" in out, "no sim ERP must be a note, not a failure: the demo starts its own"
    assert "ready: the offline demo runs" in out
    assert "pip install playwright" not in out, "the browser path is not asked for, so do not suggest it"


def test_doctor_asks_for_playwright_only_when_the_browser_is_wanted(capsys) -> None:
    assert doctor.main(["--browser"]) == (0 if doctor.importlib.util.find_spec("playwright") else 1)
    out = capsys.readouterr().out
    assert ("pip install playwright && playwright install chromium" in out) == (
        doctor.importlib.util.find_spec("playwright") is None)