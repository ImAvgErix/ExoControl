"""Persistent session, plan, checkpoint, recover."""
from __future__ import annotations

import pytest

from aether.exec_engine import ExoExecEngine
from aether import session


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("EXO_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("EXO_LOCK_DIR", str(tmp_path / "locks"))
    (tmp_path / "state").mkdir()
    yield tmp_path


def test_remember_recall(home):
    session.start("alpha", task="demo")
    assert session.remember("alpha", "editor", "notepad")["ok"] is True
    got = session.recall("alpha", "editor")
    assert got["ok"] is True
    assert got["value"] == "notepad"
    all_prefs = session.recall("alpha")
    assert all_prefs["prefs"]["editor"] == "notepad"


def test_checkpoint_and_last_focus(home):
    session.push_focus("alpha", {"title": "Notepad", "pid": 12, "window_id": 99})
    cp = session.checkpoint("alpha", url="https://example.com", note_text="mid-task")
    assert cp["ok"] is True
    loaded = session.get_checkpoint("alpha")
    assert loaded["url"] == "https://example.com"
    assert session.last_focus("alpha")["title"] == "Notepad"


def test_plan_roundtrip(home):
    out = session.set_plan("alpha", "file taxes", steps=[{"op": "launch", "app": "notepad"}])
    assert out["ok"] is True
    st = session.status("alpha")
    assert st["session"]["plan"]["goal"] == "file taxes"


def test_session_ops_via_exec(home):
    eng = ExoExecEngine()
    out = eng.execute(
        [
            {"op": "session_start", "agent_id": "beta", "task": "own-pc"},
            {"op": "remember", "agent_id": "beta", "key": "theme", "value": "dark"},
            {"op": "recall", "agent_id": "beta", "key": "theme"},
            {"op": "plan", "agent_id": "beta", "goal": "open docs"},
            {"op": "checkpoint", "agent_id": "beta", "path": "C:\\tmp"},
            {"op": "session_status", "agent_id": "beta"},
        ]
    )
    assert out["ok"] is True
    assert out["steps"][2]["result"]["value"] == "dark"
    assert out["steps"][5]["result"]["session"]["plan"]["goal"] == "open docs"


def test_recover_needs_lease(home):
    session.push_focus("gamma", {"title": "x"})
    eng = ExoExecEngine()
    out = eng.execute([{"op": "recover", "agent_id": "gamma"}])
    assert out["steps"][0]["result"]["ok"] is False
    assert "lease" in out["steps"][0]["result"]["error"]


def test_session_ops_via_distinct_names(home):
    eng = ExoExecEngine()
    out = eng.execute(
        [
            {"op": "session_start", "agent_id": "delta", "task": "own-pc"},
            {"op": "remember", "agent_id": "delta", "key": "theme", "value": "dark"},
            {"op": "session_recall", "agent_id": "delta", "key": "theme"},
            {"op": "plan", "agent_id": "delta", "goal": "open docs"},
            {"op": "session_checkpoint", "agent_id": "delta", "path": "C:\\tmp"},
            {"op": "session_memory_status", "agent_id": "delta"},
            {"op": "session_memory_end", "agent_id": "delta"},
        ]
    )
    assert out["ok"] is True
    assert out["steps"][2]["result"]["value"] == "dark"
    assert out["steps"][5]["result"]["session"]["plan"]["goal"] == "open docs"
    assert out["steps"][6]["result"]["ok"] is True


def test_session_status_without_agent_is_seat(home):
    eng = ExoExecEngine()
    body = eng.execute([{"op": "session_status"}])["steps"][0]["result"]
    assert body["ok"] is True
    assert "held" in body
    assert "seated" in body
    assert "session" not in body

