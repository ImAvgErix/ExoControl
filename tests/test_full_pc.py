"""Multi-surface Full-PC workflow: trust + files + session + os_info + catalog."""
from __future__ import annotations

import pytest

from aether.exec_engine import ExoExecEngine
from aether.ops_catalog import known_ops, list_ops
from aether import os_ops, trust


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("EXO_HOME", str(tmp_path / "exo"))
    monkeypatch.setenv("EXO_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("EXO_LOCK_DIR", str(tmp_path / "locks"))
    monkeypatch.setenv("EXO_FILE_ROOTS", str(tmp_path / "workspace"))
    monkeypatch.delenv("EXO_TRUST", raising=False)
    monkeypatch.delenv("EXO_FULL_TRUST", raising=False)
    (tmp_path / "workspace").mkdir()
    (tmp_path / "state").mkdir()
    yield tmp_path


def test_catalog_includes_new_ops():
    names = known_ops()
    for op in (
        "trust_status", "web_task", "os_info", "files_mkdir", "window_snap",
        "session_start", "remember", "recover", "browser_extract", "browser_tabs",
    ):
        assert op in names
    detail = list_ops(detail=True)
    assert detail["count"] >= 70
    rules = " ".join(detail["rules"])
    assert "Full-Trust" in rules or "full" in rules.lower()


def test_os_info_and_which(home):
    info = os_ops.os_info()
    assert info["ok"] is True
    assert "trust" in info
    w = os_ops.which("python")
    # python may or may not be on PATH in every CI image; ok either way
    assert "ok" in w


def test_files_mkdir_stat_search(home):
    eng = ExoExecEngine()
    ws = home / "workspace"
    out = eng.execute(
        [
            {"op": "lease_acquire", "agent_id": "pc", "task": "files", "ttl_sec": 30},
            {"op": "files_mkdir", "path": str(ws / "notes")},
            {"op": "files_write", "path": str(ws / "notes" / "a.txt"), "text": "hi"},
            {"op": "files_exists", "path": str(ws / "notes" / "a.txt")},
            {"op": "files_stat", "path": str(ws / "notes" / "a.txt")},
            {"op": "files_search", "path": str(ws / "notes"), "pattern": "*.txt"},
            {"op": "os_info"},
            {"op": "session_start", "agent_id": "pc", "task": "files"},
            {"op": "remember", "key": "last_dir", "value": "notes"},
            {"op": "lease_release"},
        ]
    )
    assert out["ok"] is True, out
    assert out["steps"][3]["result"]["exists"] is True
    assert out["steps"][4]["result"]["is_file"] is True
    assert out["steps"][5]["result"]["count"] >= 1
    assert out["steps"][6]["result"]["ok"] is True


def test_help_mentions_web_task(home):
    eng = ExoExecEngine()
    out = eng.execute([{"op": "help", "query": "web_task", "detail": True}])
    body = out["steps"][0]["result"]
    assert any(o["op"] == "web_task" for o in body["ops"])


def test_cli_trust_status(home, capsys):
    from exo_control.cli import main

    rc = main(["trust", "status"])
    assert rc == 0
    captured = capsys.readouterr().out
    assert "level" in captured
