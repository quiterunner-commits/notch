from conftest import FakeHttp, FakeResp

from book.modules import task_io
from book.modules.task_io import Task

RELAY = "http://relay"


def test_run_success_sets_done():
    t = Task(title="A")
    ev = t.run(lambda: 42)
    assert ev.ok and ev.output == 42 and t.state == "done"


def test_run_failure_sets_blocked():
    t = Task(title="B")
    assert not t.run(lambda: 1 / 0).ok and t.state == "blocked"


def test_note_has_no_body():
    t = Task(title="N", kind="note")
    assert t.run().ok and t.state == "draft"


def test_list_tasks_maps_hub_proposals():
    http = FakeHttp({("GET", f"{RELAY}/v1/actions/proposals"): FakeResp(200, {"items": [
        {"proposal_id": "p2", "intent": "second", "state": "awaiting", "metadata": {"priority": 2}},
        {"proposal_id": "p1", "title": "first", "state": "approved", "capability": "voice.send",
         "scope_sha256": "abc", "metadata": {"priority": 1, "comments": ["hi"]}},
    ]})})
    tasks, err = task_io.list_tasks(http, RELAY, {})
    assert err is None
    assert [t.id for t in tasks] == ["p1", "p2"]
    assert tasks[0].kind == "proposal" and tasks[0].capability == "voice.send"
    assert tasks[0].comments == ["hi"]


def test_list_tasks_401_asks_for_passkey():
    http = FakeHttp({("GET", f"{RELAY}/v1/actions/proposals"): FakeResp(401)})
    tasks, err = task_io.list_tasks(http, RELAY, {})
    assert tasks == [] and err == task_io.NO_IDENTITY


def test_propose_turns_draft_into_hub_task():
    http = FakeHttp({("POST", f"{RELAY}/v1/actions/proposals"): FakeResp(200, {"proposal_id": "p9", "state": "awaiting"})})
    t = Task(title="deploy db", kind="shell", priority=1, comments=["only via tunnel"])
    t, err = task_io.propose(http, RELAY, {}, t)
    assert err is None and t.id == "p9" and t.state == "awaiting" and t.kind == "proposal"
    sent = http.calls[0][2]
    assert sent["capability"] == "task.shell" and sent["metadata"]["comments"] == ["only via tunnel"]


def test_columns_groups_by_state():
    cols = task_io.columns([Task(title="a"), Task(title="b", state="awaiting")])
    assert len(cols["draft"]) == 1 and len(cols["awaiting"]) == 1
