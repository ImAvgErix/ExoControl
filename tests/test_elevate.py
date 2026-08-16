"""Elevated broker client — no UAC in unit tests."""
from __future__ import annotations

from exo_control import elevate, trust


def test_default_does_not_escalate(monkeypatch, tmp_path):
    monkeypatch.setenv("EXO_HOME", str(tmp_path / "exo"))
    monkeypatch.setenv("EXO_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.delenv("EXO_TRUST", raising=False)
    monkeypatch.delenv("EXO_FULL_TRUST", raising=False)
    monkeypatch.setenv("EXO_DISABLE_ELEVATE", "1")
    (tmp_path / "state").mkdir()
    assert elevate.should_escalate() is False
    assert elevate.unrestricted() is False


def test_full_trust_would_escalate_unless_disabled(monkeypatch, tmp_path):
    monkeypatch.setenv("EXO_HOME", str(tmp_path / "exo"))
    monkeypatch.setenv("EXO_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("EXO_TRUST", "full")
    monkeypatch.delenv("EXO_DISABLE_ELEVATE", raising=False)
    (tmp_path / "state").mkdir()
    trust.enable_full_trust(ack="I own this PC", confirm=True, source="test")
    assert trust.full_trust_active() is True
    monkeypatch.setenv("EXO_DISABLE_ELEVATE", "1")
    assert elevate.should_escalate() is False
    assert elevate.unrestricted() is True


def test_looks_access_denied():
    assert elevate.looks_access_denied({"ok": False, "error": "Access is denied."})
    assert elevate.looks_access_denied({"ok": False, "stderr": "ERROR: Access is denied."})
    assert not elevate.looks_access_denied({"ok": False, "error": "key not found"})
    assert not elevate.looks_access_denied({"ok": True})


def test_dispatch_ping():
    out = elevate.dispatch("ping", {})
    assert out["ok"] is True
    assert out.get("pong") is True


def test_dispatch_unknown():
    out = elevate.dispatch("nope", {})
    assert out["ok"] is False


def test_handle_request_bad_token(monkeypatch, tmp_path):
    monkeypatch.setenv("EXO_HOME", str(tmp_path / "exo"))
    monkeypatch.setenv("EXO_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.delenv("EXO_KILL_SWITCH", raising=False)
    (tmp_path / "state").mkdir()
    out = elevate.handle_request({"token": "nope", "op": "ping"}, "secret")
    assert out["ok"] is False
    assert out["error"] == "elevate_bad_token"


def test_handle_request_good_token(monkeypatch, tmp_path):
    monkeypatch.setenv("EXO_HOME", str(tmp_path / "exo"))
    monkeypatch.setenv("EXO_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.delenv("EXO_KILL_SWITCH", raising=False)
    (tmp_path / "state").mkdir()
    out = elevate.handle_request({"token": "secret", "op": "ping"}, "secret")
    assert out["ok"] is True


def test_broker_python_prefers_pythonw(tmp_path, monkeypatch):
    py = tmp_path / "python.exe"
    pyw = tmp_path / "pythonw.exe"
    py.write_bytes(b"")
    pyw.write_bytes(b"")
    monkeypatch.setattr(elevate.sys, "executable", str(py))
    assert elevate.broker_python_exe() == str(pyw)


def test_broker_python_falls_back_without_pythonw(tmp_path, monkeypatch):
    py = tmp_path / "python.exe"
    py.write_bytes(b"")
    monkeypatch.setattr(elevate.sys, "executable", str(py))
    assert elevate.broker_python_exe() == str(py)


def test_task_xml_uses_windowless_python():
    xml = elevate._task_xml(r"C:\Python\pythonw.exe")
    assert "pythonw.exe" in xml
    assert "-m exo_control.elevated_broker --serve" in xml
    assert "python.exe" not in xml
    assert "<Hidden>true</Hidden>" in xml


def test_kill_file_blocks_broker(monkeypatch, tmp_path):
    monkeypatch.setenv("EXO_HOME", str(tmp_path / "exo"))
    monkeypatch.setenv("EXO_STATE_DIR", str(tmp_path / "state"))
    (tmp_path / "state").mkdir()
    trust.arm_kill_file()
    out = elevate.handle_request({"token": "secret", "op": "ping"}, "secret")
    assert out["ok"] is False
    assert out["error"] == "kill_switch"
