"""task_io: Task поверх proposal хаба — без marimo, на подменённом httpx."""

import json

import httpx
import pytest

from conftest import ROOT  # noqa: F401 — sys.path на корень
from book.modules import hub_io, task_io
from book.modules.task_io import Task

RELAY = "http://relay"
PROPOSALS = "/v1/actions/proposals"


@pytest.fixture
def http(fake_relay):
    """httpx.Client уже подменён conftest'ом на MockTransport."""
    return httpx.Client(timeout=1.0)


# ─── локальный круг: draft → done | blocked ───────────────────────────────

def test_new_task_is_local_draft():
    t = Task(title="посчитать")
    assert t.state == "draft" and t.id.startswith("draft-") and not t.is_hub
    assert t.effective_capability() == "task.func"


def test_source_is_recorded():
    assert Task(title="x", source="voice").source == "voice"


def test_run_success_sets_done():
    t = Task(title="A")
    evidence = t.run(lambda: 42)
    assert evidence.ok and evidence.output == 42 and t.state == "done"


def test_run_failure_sets_blocked_with_reason():
    t = Task(title="B")
    evidence = t.run(lambda: 1 / 0)
    assert not evidence.ok and t.state == "blocked"
    assert "ZeroDivisionError" in evidence.output


def test_note_without_body_stays_draft():
    t = Task(title="N", kind="note")
    assert t.run().ok and t.state == "draft"


def test_shell_task_refuses_local_run():
    """Внешний эффект — только через propose → approve, не через run()."""
    t = Task(title="rm -rf", kind="shell")
    evidence = t.run(lambda: "выполнено")
    assert not evidence.ok and t.state == "blocked" and "propose" in evidence.output


def test_priority_is_bounded():
    with pytest.raises(ValueError):
        Task(title="x", priority=9)


# ─── форма proposal — как у gated_bridge (единственный клиент POST) ───────

def test_to_proposal_matches_hub_shape():
    t = Task(title="Поднять Postgres", kind="shell", priority=2, owner="human",
             comments=["порт только через туннель"], depends_on=["draft-1"])
    body = t.to_proposal()
    assert set(body) == {"capability", "title", "actor", "external_effect", "reversible", "intent"}
    assert body["capability"] == "task.shell"
    assert body["actor"] == {"kind": "user", "ref": task_io.ACTOR_REF}
    assert body["external_effect"] is True and body["reversible"] is False
    assert body["intent"]["kind"] == "shell" and body["intent"]["priority"] == 2
    assert body["intent"]["comments"] == ["порт только через туннель"]
    assert body["intent"]["draft_id"] == t.id
    assert len(body["intent"]) <= 16, "intent у хаба — объект до 16 полей"


def test_agent_note_is_local_and_reversible():
    body = Task(title="заметка", kind="note").to_proposal()
    assert body["actor"]["kind"] == "agent"
    assert body["external_effect"] is False and body["reversible"] is True


def test_from_proposal_reads_hub_fields():
    t = task_io.from_proposal({
        "proposal_id": "p1", "title": "открыть дверь", "state": "approved",
        "capability": "door", "scope_sha256": "deadbeef" * 4, "created_at": "2026-09-03T10:00:00Z",
        "intent": {"kind": "shell", "priority": 1, "owner": "human", "comments": ["hi"]},
    })
    assert t.id == "p1" and t.state == "approved" and t.is_hub
    assert t.kind == "shell" and t.owner == "human" and t.priority == 1
    assert t.capability == "door" and t.comments == ["hi"]
    assert t.occurred_at == "2026-09-03T10:00:00Z"


def test_from_proposal_tolerates_foreign_shape():
    """Предложения не из книги (гейт агента, voice): intent — чужой объект."""
    t = task_io.from_proposal({"id": "p2", "capability": "notch.agent.tool",
                               "intent": {"detail": "ls -la", "tool": "Bash"}})
    assert t.id == "p2" and t.title == "ls -la" and t.kind == "proposal"
    assert t.state == "awaiting" and t.priority == 3
    assert task_io.from_proposal({"title": "без id"}) is None


# ─── list_tasks: реестр = хаб ─────────────────────────────────────────────

def test_list_tasks_maps_and_orders(fake_relay, http):
    fake_relay[PROPOSALS] = (200, {"proposals": [
        {"proposal_id": "p2", "title": "second", "state": "approved", "intent": {"priority": 2}},
        {"proposal_id": "p1", "title": "first", "state": "awaiting", "intent": {"priority": 1}},
        {"proposal_id": "p2", "title": "second", "state": "approved"},  # дубль между state-запросами
        {"title": "без id"},
    ]})
    listing = task_io.list_tasks(http, RELAY, {})
    assert listing["ok"]
    assert [t.id for t in listing["tasks"]] == ["p1", "p2"]
    assert listing["tasks"][0].state == "awaiting"


def test_list_tasks_401_is_no_identity(fake_relay, http):
    fake_relay[PROPOSALS] = (401, {"error": "unauthorized"})
    listing = task_io.list_tasks(http, RELAY, {})
    assert not listing["ok"] and listing["tasks"] == []
    assert listing["reason"] == task_io.NO_IDENTITY == hub_io.NO_IDENTITY


def test_list_tasks_other_refusal_quotes_hub(fake_relay, http):
    fake_relay[PROPOSALS] = (503, {"error": "relay.db locked"})
    listing = task_io.list_tasks(http, RELAY, {}, states=("awaiting",))
    assert not listing["ok"] and "503" in listing["reason"] and "relay.db" in listing["reason"]


def test_list_tasks_hub_down_raises_like_chats(fake_relay, http):
    with pytest.raises(httpx.ConnectError):
        task_io.list_tasks(http, RELAY, {})


# ─── propose: черновик → awaiting ─────────────────────────────────────────

def test_propose_turns_draft_into_hub_task():
    """Свой транспорт вместо fake_relay: нужно увидеть тело и заголовок запроса."""
    sent = {}

    def handler(request: httpx.Request) -> httpx.Response:
        sent["method"] = request.method
        sent["path"] = request.url.path
        sent["auth"] = request.headers.get("authorization")
        sent["body"] = json.loads(request.content)
        return httpx.Response(201, json={"proposal": {
            "id": "p9", "state": "awaiting", "capability": "task.shell", "scope_sha256": "abc",
        }})

    http = httpx.Client(transport=httpx.MockTransport(handler))
    draft = Task(title="deploy db", kind="shell", priority=1, owner="human")
    result = task_io.propose(http, RELAY, hub_io.auth_headers("desk-sess"), draft)
    assert result["ok"], result["reason"]
    accepted = result["task"]
    assert accepted.id == "p9" and accepted.state == "awaiting" and accepted.is_hub
    assert accepted.scope_sha256 == "abc"
    assert draft.state == "draft", "черновик не мутируется — хаб вернул новую задачу"
    assert sent["method"] == "POST" and sent["path"] == PROPOSALS
    assert sent["auth"] == "Bearer desk-sess"
    assert sent["body"]["capability"] == "task.shell" and sent["body"]["actor"]["kind"] == "user"


def test_propose_401_is_no_identity(fake_relay, http):
    fake_relay[PROPOSALS] = (401, {})
    result = task_io.propose(http, RELAY, {}, Task(title="x"))
    assert not result["ok"] and result["reason"] == task_io.NO_IDENTITY
    assert result["task"].state == "draft"


def test_propose_without_id_is_refusal(fake_relay, http):
    fake_relay[PROPOSALS] = (200, {"proposal": {"title": "нет id"}})
    result = task_io.propose(http, RELAY, {}, Task(title="x"))
    assert not result["ok"] and "идентификатор" in result["reason"]


def test_propose_refuses_hub_task(fake_relay, http):
    t = Task(id="p1", title="уже там", state="awaiting")
    result = task_io.propose(http, RELAY, {}, t)
    assert not result["ok"] and "уже в хабе" in result["reason"]


# ─── окружение: credential из hub_io ──────────────────────────────────────

def test_environment_prefers_session(monkeypatch, tmp_path):
    session_file = tmp_path / "session.json"
    session_file.write_text(json.dumps({"session": "desk-sess-1"}), encoding="utf-8")
    monkeypatch.setenv("WFORK_SESSION_PATH", str(session_file))
    monkeypatch.setenv("WFORK_RELAY_TOKEN", "device-token")
    monkeypatch.setenv("WFORK_RELAY_URL", "http://hub:8765/")
    env = task_io.environment()
    assert env["token"] == "desk-sess-1" and env["source"] == "session"
    assert env["headers"] == {"Authorization": "Bearer desk-sess-1"}
    assert env["relay_url"] == "http://hub:8765"


def test_environment_without_identity_has_no_header(monkeypatch):
    monkeypatch.delenv("WFORK_SESSION_PATH", raising=False)
    monkeypatch.delenv("WFORK_RELAY_TOKEN", raising=False)
    env = task_io.environment()
    assert env["token"] == "" and env["source"] == "" and env["headers"] == {}


# ─── доска ────────────────────────────────────────────────────────────────

def test_columns_keep_empty_states_in_order():
    cols = task_io.columns([Task(title="a"), Task(title="b", state="awaiting", id="p1")])
    assert list(cols)[:2] == ["awaiting", "draft"]
    assert len(cols["awaiting"]) == 1 and len(cols["draft"]) == 1 and cols["rejected"] == []


def test_rows_are_flat():
    row = task_io.rows([Task(title="a", kind="shell", scope_sha256="0123456789abcdef")])[0]
    assert row["effect"] == "внешний" and row["scope"] == "0123456789ab"
    assert all(not isinstance(v, (dict, list)) for v in row.values())


def test_format_proposed():
    t = Task(id="p9", title="deploy", state="awaiting")
    assert "p9" in task_io.format_proposed({"ok": True, "task": t})
    assert task_io.format_proposed({"ok": False, "reason": "нет"}) == "🔴 нет"
