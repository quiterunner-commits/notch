"""/board: доска задач поверх proposals хаба, на подменённом httpx."""

import json

from conftest import run_book_module

PROPOSALS = "/v1/actions/proposals"


def test_no_identity_hides_tasks(fake_relay, monkeypatch):
    monkeypatch.delenv("WFORK_RELAY_TOKEN", raising=False)
    monkeypatch.delenv("WFORK_SESSION_PATH", raising=False)
    _, defs = run_book_module("book.modules.board")
    assert defs["token"] == ""
    assert defs["tasks"] == [] and not defs["listing"]["ok"]


def test_session_beats_device_token(fake_relay, monkeypatch, tmp_path):
    session_file = tmp_path / "session.json"
    session_file.write_text(json.dumps({"session": "desk-sess-1"}), encoding="utf-8")
    monkeypatch.setenv("WFORK_SESSION_PATH", str(session_file))
    monkeypatch.setenv("WFORK_RELAY_TOKEN", "device-token")
    fake_relay[PROPOSALS] = (200, {"proposals": []})
    _, defs = run_book_module("book.modules.board")
    assert defs["token"] == "desk-sess-1"
    assert defs["headers"] == {"Authorization": "Bearer desk-sess-1"}
    assert defs["env"]["source"] == "session"


def test_board_lists_hub_tasks(fake_relay, monkeypatch):
    monkeypatch.setenv("WFORK_RELAY_TOKEN", "tok")
    monkeypatch.delenv("WFORK_SESSION_PATH", raising=False)
    fake_relay[PROPOSALS] = (200, {"proposals": [
        {"proposal_id": "p1", "title": "открыть дверь", "capability": "door",
         "state": "awaiting", "scope_sha256": "deadbeef" * 4},
        {"proposal_id": "p2", "title": "агент: ls", "state": "approved",
         "intent": {"kind": "shell", "owner": "agent"}},
    ]})
    _, defs = run_book_module("book.modules.board")
    assert defs["listing"]["ok"]
    assert [t.id for t in defs["tasks"]] == ["p1", "p2"]
    assert defs["tasks"][0].state == "awaiting" and defs["tasks"][1].kind == "shell"
    assert defs["board"] is not None and defs["table"] is not None


def test_board_401_asks_for_passkey(fake_relay, monkeypatch):
    monkeypatch.setenv("WFORK_RELAY_TOKEN", "stale")
    monkeypatch.delenv("WFORK_SESSION_PATH", raising=False)
    fake_relay[PROPOSALS] = (401, {"error": "unauthorized"})
    _, defs = run_book_module("book.modules.board")
    assert defs["tasks"] == []
    assert "passkey" in defs["listing"]["reason"]


def test_board_survives_hub_down(fake_relay, monkeypatch):
    monkeypatch.setenv("WFORK_RELAY_TOKEN", "tok")
    monkeypatch.delenv("WFORK_SESSION_PATH", raising=False)
    _, defs = run_book_module("book.modules.board")  # маршрутов нет → ConnectError
    assert defs["tasks"] == [] and "ConnectError" in defs["listing"]["reason"]


def test_form_widgets_exist(fake_relay, monkeypatch):
    monkeypatch.setenv("WFORK_RELAY_TOKEN", "tok")
    monkeypatch.delenv("WFORK_SESSION_PATH", raising=False)
    fake_relay[PROPOSALS] = (200, {"proposals": []})
    _, defs = run_book_module("book.modules.board")
    assert defs["kind"].value == "note" and defs["priority"].value == 3
    assert defs["submit"].value is False, "без нажатия в хаб ничего не уходит"
