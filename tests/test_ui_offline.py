"""The demo page, driven over HTTP exactly as a browser drives it. No browser, no API key.

The page itself plans **online** (the model writes the plan, `plan_source` names it); this file
pins the deterministic no-key path so the suite needs neither a key nor a socket.

Driven the way the page drives it — `POST /api/run`, poll `/api/state` until a request is queued,
`POST /api/approve`, poll until the verdict lands — so the numbers asserted here are the ones the
BUILD asserts on screen: `pass 8/8`, one ERP row, evidence on disk, and a second Run that replays
both steps (`replayed=2`) without posting a second row.

Phase 13 adds the storytelling the page tells with no context: the eight-stage strip is read off
the run's own events, the planner badge is the run's own `plan_source`, and the gallery states each
job's tool chain before you click it.
"""

from __future__ import annotations

import inspect
import json
import os
import shutil
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.cli import main as cli  # noqa: E402
from src.reliability import hitl  # noqa: E402
from src.ui import app as ui  # noqa: E402


@pytest.fixture
def page():
    """The real page on an OS-picked port, over a sim ERP the test owns.

    The scratch is a real `/tmp` directory, not pytest's `tmp_path`: `cli.fresh` refuses to delete
    anything outside a scratch root, so a `tmp_path` scratch is silently never wiped and "cold" would
    be a word rather than a fact. The servers and that directory are both shut down here, so a test
    that fails mid-run leaks no listener and no file.
    """
    from sim_app.server import make_server

    # One scratch root, exactly like `python3 -m src.ui.app`: the ERP db sits inside the dir the
    # page wipes, so a cold start really is cold all the way down to the posted rows.
    scratch = Path(tempfile.mkdtemp(prefix="centralign-ui-test-", dir="/tmp"))
    erp = make_server("127.0.0.1", 0, scratch / "scratch" / "sim.db")
    threading.Thread(target=erp.serve_forever, daemon=True).start()
    # `offline=True` is the page's own default turned the other way, and only for this fixture: the
    # suite must not need a key or a socket, and `plan_source` must be the one value it pins.
    demo = ui.Demo(scratch=scratch / "scratch", erp_url=f"http://127.0.0.1:{erp.server_address[1]}",
                   offline=True)
    server = ui.serve(demo)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    assert server.server_address[0] == "127.0.0.1", "the page approves money; it is never routable"
    try:
        yield base
    finally:
        server.shutdown()
        server.server_close()
        demo.close()
        erp.shutdown()
        erp.server_close()
        shutil.rmtree(scratch, ignore_errors=True)
        os.environ.pop("ERP_URL", None)


def state(base: str) -> dict[str, Any]:
    with urllib.request.urlopen(f"{base}/api/state", timeout=5) as resp:
        assert resp.status == 200
        return json.loads(resp.read())


def post(base: str, path: str, body: dict[str, Any] | None = None) -> tuple[int, dict[str, Any]]:
    req = urllib.request.Request(
        f"{base}{path}", data=json.dumps(body or {}).encode(), method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def until(base: str, pred: Callable[[dict[str, Any]], bool], timeout: float = 90.0) -> dict[str, Any]:
    """Poll `/api/state` the way the page does, until the run reaches the state we care about."""
    deadline, last = time.monotonic() + timeout, {}
    while time.monotonic() < deadline:
        last = state(base)
        if pred(last):
            return last
        time.sleep(0.05)
    raise AssertionError(f"timed out after {timeout}s; last state: {json.dumps(last)[:400]}")


def replayed(s: dict[str, Any]) -> int:
    return sum(1 for row in s["steps"] if row["status"] == "cached")


# ------------------------------------------------------------------------ page
def test_the_page_is_one_html_file_and_unknown_routes_are_refused(page: str) -> None:
    with urllib.request.urlopen(page, timeout=5) as resp:
        assert resp.status == 200
        assert resp.headers.get("Content-Type", "").startswith("text/html")
        body = resp.read().decode("utf-8")
    assert "Run the task" in body and "/api/state" in body

    try:
        urllib.request.urlopen(f"{page}/nope", timeout=5)
        raise AssertionError("an unknown route must not answer 200")
    except urllib.error.HTTPError as exc:
        assert exc.code == 404


def test_run_then_approve_passes_8_of_8_and_posts_exactly_one_row(page: str) -> None:
    status, started = post(page, "/api/run")
    assert status == 202 and started["phase"] == "running", started

    waiting = until(page, lambda s: s["phase"] == "awaiting")
    request = waiting["pending"][0]
    assert request["tool"] == "erp_post_invoice" and request["amount"] == 4820.0, request
    assert waiting["erp"]["count"] == 0, "a queued request must never reach the money path"
    assert waiting["banner"].startswith("blocked"), waiting["banner"]

    status, _ = post(page, "/api/approve", {"request_id": request["request_id"], "approver": "tester"})
    assert status == 200

    done = until(page, lambda s: s["phase"] == "done" and s["done"])
    assert done["banner"] == "pass 8/8", done["banner"]
    assert replayed(done) == 1, "the resume replays the read; only the post executes for real"
    assert done["erp"]["count"] == 1, "a second row would mean the page double-posted"
    assert done["steps"][-1]["detail"].startswith("ERP row #1 created"), done["steps"]

    evidence = Path(done["evidence_path"])
    bundle = json.loads(evidence.read_text(encoding="utf-8"))
    assert bundle["verdict"]["status"] == "pass"
    assert bundle["totals"]["tools_actually_executed"] == ["erp_post_invoice"], bundle["totals"]

    closed = [r for r in hitl.read(demo_queue(page)) if r.get("queue") == hitl.CLOSED]
    assert [r["approver"] for r in closed] == ["tester"], "the audit trail says who signed off"


def test_a_second_run_replays_both_steps_and_posts_nothing_new(page: str) -> None:
    run_once(page)
    post(page, "/api/run")
    done = until(page, lambda s: s["phase"] == "done" and s["done"])

    assert done["banner"] == "pass 8/8", done["banner"]
    assert replayed(done) == 2, "a warm run replays the read and the post"
    assert done["erp"]["count"] == 1, "a replay must not create a second ERP row"
    assert done["pending"] == [], "nothing is left to approve: both steps replay"


# ----------------------------------------------------------------------- edges
def test_the_button_can_only_close_the_request_the_card_names(page: str) -> None:
    post(page, "/api/run")
    waiting = until(page, lambda s: s["phase"] == "awaiting")

    assert post(page, "/api/approve", {"request_id": "not-a-request", "approver": "tester"})[0] == 409
    assert post(page, "/api/approve")[0] == 409, "no request id at all is a refusal, not a blank cheque"
    assert state(page)["erp"]["count"] == 0, "none of those refusals posted anything"

    # A blank name is not a refusal: it is recorded as whoever is signed in, so a decision is
    # never unowned — the same rule the CLI prompt follows.
    post(page, "/api/approve", {"request_id": waiting["pending"][0]["request_id"]})
    closed = [r for r in hitl.read(demo_queue(page)) if r.get("queue") == hitl.CLOSED]
    assert [r["approver"] for r in closed] == [cli.approver_name()], closed


def test_a_second_click_while_a_run_is_in_flight_is_refused(page: str) -> None:
    assert post(page, "/api/run")[0] == 202
    until(page, lambda s: s["phase"] == "awaiting")
    status, body = post(page, "/api/run")
    assert status == 409 and "already in flight" in body["error"], body


def test_the_page_cannot_be_bound_off_localhost() -> None:
    with pytest.raises(SystemExit):
        ui.main(["--host", "0.0.0.0"])


# ----------------------------------------------------------------------- the story
def event(kind: str, **payload: Any) -> dict[str, Any]:
    """One ledger event, the shape `stages_of` reads."""
    return {"type": kind, "payload": payload}


CLEAN_RUN = [
    event("run.started"), event("step.planned"), event("run.stage", stage="execute"),
    event("run.stage", stage="observe"), event("verify.checked"), event("run.completed"),
]
# A clean run never enters adapt, so the strip reads all eight minus that one.
UP_TO_VERIFY = ["goal", "understand", "plan", "execute", "observe", "verify"]


def test_the_gallery_states_each_job_before_you_click_it(page: str) -> None:
    with urllib.request.urlopen(page, timeout=5) as resp:
        body = resp.read().decode("utf-8")
    assert "How it works" in body and "Pick a job" in body
    assert all(name in body for name in ui.STAGES), "all eight loop stages are on the page"

    state_now = state(page)
    assert [sc["id"] for sc in state_now["scenarios"]] == ["intake", "inbox", "check"]
    assert state_now["scenario"] == "intake" and state_now["task"] == cli.DEFAULT_TASK
    for sc in state_now["scenarios"]:
        assert sc["title"] and sc["chain"] and sc["gate"], sc  # what it runs, said up front
    intake, inbox, check = state_now["scenarios"]
    assert "find the latest invoice" in intake["chain"] and "ERP" in intake["chain"]
    assert "approval" in intake["gate"] and inbox["gate"].startswith("read-only")
    assert "post" not in check["task"] and "erp" not in check["task"], \
        "a read-only job must not ask for a post, or the intake template claims it"


def test_the_strip_reports_the_stages_the_run_reached() -> None:
    assert ui.stages_of({"status": "completed"}, CLEAN_RUN) == UP_TO_VERIFY + ["complete"]
    # A run holding on a human is `blocked`: the strip must not light Complete on it.
    held = ui.stages_of({"status": "blocked"}, CLEAN_RUN[:-1] + [event("run.failed")])
    assert held == UP_TO_VERIFY, held
    # Adapt is entered only by a retry; a resume event is not a stage and is ignored.
    retried = CLEAN_RUN[:3] + [event("run.stage", stage="adapt")] + CLEAN_RUN[3:]
    assert "adapt" in ui.stages_of({"status": "completed"}, retried)
    assert ui.stages_of({"status": "completed"}, [event("run.stage", stage="resume")]) == []


def test_the_strip_lights_up_over_the_whole_session(page: str) -> None:
    post(page, "/api/run")
    waiting = until(page, lambda s: s["phase"] == "awaiting")
    assert waiting["stages"] == UP_TO_VERIFY, waiting["stages"]
    assert "complete" not in waiting["stages"], "a run holding on a human has not completed"

    post(page, "/api/approve", {"request_id": waiting["pending"][0]["request_id"], "approver": "tester"})
    done = until(page, lambda s: s["phase"] == "done" and s["done"])
    assert done["stages"] == UP_TO_VERIFY + ["complete"], done["stages"]


def test_the_planner_badge_is_the_runs_own_plan_source(page: str) -> None:
    waiting_run = run_once(page)
    bundle = json.loads(Path(waiting_run["evidence_path"]).read_text(encoding="utf-8"))
    assert bundle["run"]["plan_source"] == "heuristic"
    assert waiting_run["plan_source"] == bundle["run"]["plan_source"], \
        "the badge is evidence.run.plan_source, not a label the page chose"

    assert [s["tool"] for s in waiting_run["plan"]["steps"]] == ["invoice_find_latest", "erp_post_invoice"]
    assert all(s["intent"] for s in waiting_run["plan"]["steps"]), "every step carries its own why"
    assert waiting_run["plan"]["goal"] == waiting_run["task"]

    with urllib.request.urlopen(page, timeout=5) as resp:
        body = resp.read().decode("utf-8")
    assert "state.plan_source" in body and "run.plan_source" not in body
    # The honest-fallback wording is in the page; 13b proves it against a live LLM run.
    assert "model fallback:" in body and "deterministic planner used" in body


def test_switching_scenario_loads_its_task_and_resets_the_page(page: str) -> None:
    first = run_once(page)
    assert first["erp"]["count"] == 1 and first["evidence_path"]

    status, switched = post(page, "/api/scenario", {"id": "inbox"})
    assert status == 200 and switched["scenario"] == "inbox"
    assert switched["task"] == "list the invoice inbox in seed/invoices and parse " \
        "INV-X-2024-0703-acme.pdf and INV-Y-2024-0805-other.txt", switched["task"]
    assert switched["phase"] == "idle" and switched["run_id"] is None and switched["clicks"] == 0
    assert switched["steps"] == [] and switched["verdict"] is None and switched["evidence"] is None
    assert switched["stages"] == [] and switched["plan_source"] == "" and switched["plan"] is None
    # The reset is a real reset: the ERP itself is empty again, not just the panel.
    with urllib.request.urlopen(f"{switched['erp_url']}/invoices", timeout=5) as resp:
        assert json.loads(resp.read())["count"] == 0

    assert post(page, "/api/scenario", {"id": "nope"})[0] == 404

    post(page, "/api/run")
    read_only = until(page, lambda s: s["phase"] != "running" and s["run_id"])
    assert read_only["pending"] == [], "a read-side job never queues money for a human"
    assert read_only["erp"]["count"] == 0, "a read-side job writes nothing to the ERP"
    assert read_only["plan_source"] == "heuristic", "same planner, same badge"


def test_the_two_read_side_jobs_pass_with_no_approval_and_no_erp_write(page: str) -> None:
    """S2 and S3 generalize the operator: different asks, different plans, neither spends money."""
    for scenario_id, steps, banner_text in (("inbox", 3, "pass 9/9"), ("check", 1, "pass 7/7")):
        assert post(page, "/api/scenario", {"id": scenario_id})[0] == 200
        assert post(page, "/api/run")[0] == 202
        done = until(page, lambda s: s["phase"] == "done" and s["done"])
        assert done["banner"] == banner_text, done["banner"]
        assert len(done["steps"]) == steps and done["plan_source"] == "heuristic"
        assert done["pending"] == [], "a read-side job must never queue money for a human"
        assert done["erp"]["count"] == 0, "a read-side job must never write to the ERP"

        bundle = json.loads(Path(done["evidence_path"]).read_text(encoding="utf-8"))
        assert bundle["verdict"]["status"] == "pass"
        assert not [e for e in bundle["events"] if e["type"] == "approval.requested"], bundle["events"]
        # Every step says what it read, so the page reports totals instead of "done".
        assert all(step["detail"] for step in done["steps"]), done["steps"]


def test_the_scenario_templates_plan_reads_and_nothing_else() -> None:
    """The three gallery tasks plan honestly offline, and only the intake one can write."""
    from src.runtime.planner import check_plan, heuristic_plan, inbox_plan, intake_plan
    from src.tools import manifest_registry as reg

    manifests = reg.registry()
    risks = {name: m.risk for name, m in manifests.items()}
    templates = (intake_plan, inbox_plan, check_plan)
    for scenario in ui.SCENARIOS:
        plan = heuristic_plan(scenario["task"], manifests)
        writes = [s.tool for s in plan.steps if risks[s.tool] != "read"]
        assert writes == (["erp_post_invoice"] if scenario["id"] == "intake" else []), \
            (scenario["id"], [s.tool for s in plan.steps])
        # No template may claim a task that is not its own, so the generic path still gets a turn.
        assert sum(1 for f in templates if f(scenario["task"], manifests)) == 1, scenario["id"]

    inbox = heuristic_plan(ui.SCENARIOS[1]["task"], manifests)
    paths = [s.args["path"] for s in inbox.steps if s.tool == "invoice_parse"]
    assert paths == ["seed/invoices/INV-X-2024-0703-acme.pdf",
                     "seed/invoices/INV-Y-2024-0805-other.txt"], paths
    assert inbox.steps[0].args == {"dir": "seed/invoices", "pattern": "*"}
    # A task outside all three shapes still reaches the keyword path, untouched.
    outside = heuristic_plan("open the portal at http://127.0.0.1:8000/portal", manifests)
    assert outside.steps and outside.steps[0].intent.startswith("heuristic: "), \
        [s.tool for s in outside.steps]


def test_the_page_has_no_offline_mode() -> None:
    """`python3 -m src.ui.app` plans with the model; there is no flag that turns that off."""
    assert inspect.signature(ui.Demo).parameters["offline"].default is False, \
        "the page must ask the model unless a caller (the tests) says otherwise"
    with pytest.raises(SystemExit):  # argparse: the flag is gone, not renamed
        ui.main(["--llm"])
    source = Path(ui.__file__).read_text(encoding="utf-8")
    assert '"--llm"' not in source and '"--offline"' not in source, "no offline switch on the page"
    assert "planner online" in source, "the page says what it will do before you click anything"


def test_the_page_only_polls_while_a_run_is_in_flight() -> None:
    """No `setInterval(poll, …)`: the page polls fast while running/awaiting and stays still when done."""
    html = Path(ui.__file__).with_name("index.html").read_text(encoding="utf-8")
    assert "setInterval(poll" not in html, "a finished page must not keep hitting /api/state"
    assert "schedule(s)" in html and "onvisibilitychange" in html


# ------------------------------------------------------------------------ helpers
def demo_queue(page: str) -> str:
    """The queue file this page's own scratch run wrote (`<scratch>/gate.jsonl`)."""
    return str(Path(state(page)["scratch"]) / "gate.jsonl")


def run_once(page: str) -> dict[str, Any]:
    """One full cycle the way a person does it: Run, then Approve whatever the card names."""
    post(page, "/api/run")
    waiting = until(page, lambda s: s["phase"] == "awaiting")
    post(page, "/api/approve", {"request_id": waiting["pending"][0]["request_id"], "approver": "tester"})
    return until(page, lambda s: s["phase"] == "done" and s["done"])