"""Exo Pilot — original control-plane features (not vendor HTTP wrappers)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


@pytest.fixture
def tmp_roots(tmp_path, monkeypatch):
    monkeypatch.setenv("EXO_FILE_ROOTS", str(tmp_path))
    monkeypatch.setenv("EXO_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("EXO_LOCK_DIR", str(tmp_path / "locks"))
    monkeypatch.setenv("EXO_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("EXO_LIVE_EYES", "0")
    (tmp_path / "state").mkdir()
    (tmp_path / "locks").mkdir()
    (tmp_path / "home").mkdir()
    return tmp_path


def _engine():
    from exo_control.exec_engine import ExoExecEngine
    return ExoExecEngine()


def _result(script, eng=None):
    out = (eng or _engine()).execute(script if isinstance(script, list) else [script])
    return out


def test_pilot_catalog_is_lease_free_and_wired():
    from exo_control.ops_catalog import get_op, known_ops
    from exo_control.addon_ops import ROUTES

    names = (
        "goal", "intent", "checkpoint", "proof",
        "changed", "what_changed",
        "undo",
        "skill_save", "skill_run", "skill_list", "replay",
        "heal",
    )
    for name in names:
        spec = get_op(name)
        assert spec is not None, name
        assert spec.get("lease") is False, name
        assert name in known_ops()
        # Pilot lives on the engine, not the HTTP addon table.
        assert name not in ROUTES or name in {"heal"}  # none should be HTTP


def test_goal_checkpoint_proof(tmp_roots):
    eng = _engine()
    out = eng.execute([
        {"op": "goal", "text": "Write a note and prove it"},
        {"op": "checkpoint", "note": "started"},
        {"op": "proof"},
    ])
    assert out["ok"] is True
    proof = out["steps"][-1]["result"]
    assert proof["ok"] is True
    assert proof["goal"] == "Write a note and prove it"
    assert proof["checkpoints"][0]["note"] == "started"
    assert proof.get("done") is False
    assert out.get("pilot", {}).get("goal") == "Write a note and prove it"


def test_changed_diffs_glances(tmp_roots):
    eng = _engine()
    eng._pilot.note_glance({"title": "A", "a11y_labels": ["Save", "File"]})
    eng._pilot.note_glance({"title": "B", "a11y_labels": ["Save", "Open"]})
    body = eng.execute([{"op": "changed"}])["steps"][0]["result"]
    assert body["ok"] is True
    assert "Open" in body["added"]
    assert "File" in body["removed"]
    assert body["title_before"] == "A"
    assert body["title_after"] == "B"
    assert body["same"] is False


def test_undo_restores_files_write(tmp_roots):
    path = tmp_roots / "note.txt"
    path.write_text("hello", encoding="utf-8")
    eng = _engine()
    script = [
        {"op": "lease_acquire", "agent_id": "pilot", "task": "undo", "ttl_sec": 30},
        {"op": "files_write", "path": str(path), "text": "world"},
        {"op": "undo"},
        {"op": "lease_release"},
    ]
    out = eng.execute(script)
    assert out["ok"] is True, out.get("last_error")
    undo = next(s["result"] for s in out["steps"] if s["op"] == "undo")
    assert undo["ok"] is True
    assert path.read_text(encoding="utf-8") == "hello"


def test_undo_removes_created_file(tmp_roots):
    path = tmp_roots / "new.txt"
    eng = _engine()
    out = eng.execute([
        {"op": "lease_acquire", "agent_id": "pilot", "task": "undo-new", "ttl_sec": 30},
        {"op": "files_write", "path": str(path), "text": "fresh"},
        {"op": "undo"},
        {"op": "lease_release"},
    ])
    assert out["ok"] is True
    assert not path.exists()


def test_skill_save_and_run(tmp_roots):
    path = tmp_roots / "skill.txt"
    eng = _engine()
    first = eng.execute([
        {"op": "lease_acquire", "agent_id": "pilot", "task": "skill", "ttl_sec": 30},
        {"op": "files_write", "path": str(path), "text": "from-skill"},
        {"op": "skill_save", "name": "write-note"},
        {"op": "lease_release"},
    ])
    assert first["ok"] is True
    path.write_text("changed", encoding="utf-8")
    listed = eng.execute([{"op": "skill_list"}])["steps"][0]["result"]
    assert listed["ok"] is True
    assert "write-note" in listed["skills"]
    second = eng.execute([
        {"op": "lease_acquire", "agent_id": "pilot", "task": "replay", "ttl_sec": 30},
        {"op": "skill_run", "name": "write-note"},
        {"op": "lease_release"},
    ])
    assert second["ok"] is True
    assert path.read_text(encoding="utf-8") == "from-skill"


def test_heal_retries_last_failed_step(tmp_roots):
    path = tmp_roots / "heal.txt"
    eng = _engine()
    denied = eng.execute([{"op": "files_write", "path": str(path), "text": "healed"}])
    assert denied["ok"] is False
    assert not path.exists()
    out = eng.execute([
        {"op": "lease_acquire", "agent_id": "pilot", "task": "heal", "ttl_sec": 30},
        {"op": "heal"},
        {"op": "lease_release"},
    ])
    assert out["ok"] is True, out.get("last_error")
    heal = next(s["result"] for s in out["steps"] if s["op"] == "heal")
    assert heal["ok"] is True
    assert heal.get("retried") == "files_write"
    assert path.read_text(encoding="utf-8") == "healed"


def test_heal_fails_closed_without_error(tmp_roots):
    body = _engine().execute([{"op": "heal"}])["steps"][0]["result"]
    assert body["ok"] is False
    assert body.get("code") == "NOTHING_TO_HEAL"


def test_aether_pilot_shim():
    import aether.pilot_ops as shim
    import exo_control.pilot_ops as impl
    assert shim.Pilot is impl.Pilot
