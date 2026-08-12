"""Every exec op result is a dict with ok=..."""
from __future__ import annotations

from aether.exec_engine import ExoExecEngine, _normalize_result


def test_normalize_list_windows():
    out = _normalize_result("windows", [{"title": "x"}])
    assert out["ok"] is True
    assert out["windows"][0]["title"] == "x"
    assert out["count"] == 1


def test_normalize_dict_adds_ok():
    out = _normalize_result("status", {"version": "1.1.0"})
    assert out["ok"] is True
    assert out["version"] == "1.1.0"


def test_windows_op_returns_dict(tmp_path, monkeypatch):
    monkeypatch.setenv("EXO_LOCK_DIR", str(tmp_path / "locks"))
    monkeypatch.setenv("EXO_STATE_DIR", str(tmp_path / "state"))
    eng = ExoExecEngine()
    r = eng.execute([{"op": "windows"}])
    assert r["ok"] is True
    body = r["steps"][0]["result"]
    assert isinstance(body, dict)
    assert body.get("ok") is True
    assert "windows" in body
    assert "count" in body
    assert r["steps"][0]["ok"] is True


def test_exo_exec_engine_alias():
    from aether.exec_engine import AetherExecEngine, ExoExecEngine
    assert AetherExecEngine is ExoExecEngine
