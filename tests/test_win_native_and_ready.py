"""Real Windows natives + honest ready map + Pilot heal glance."""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

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
    return tmp_path


def _engine():
    from exo_control.exec_engine import ExoExecEngine
    return ExoExecEngine()


def _result(script, eng=None):
    return (eng or _engine()).execute(script if isinstance(script, list) else [script])["steps"][0]["result"]


def test_parse_netsh_and_netstat():
    from exo_control.win_native import parse_netsh_wlan, parse_netstat_listening

    wifi = parse_netsh_wlan(
        "There is 1 interface on the system:\n\n"
        "    Name                   : Wi-Fi\n"
        "    State                  : connected\n"
        "    SSID                   : HomeNet\n"
        "    Signal                 : 88%\n"
    )
    assert wifi["ok"] is True
    assert wifi["ssid"] == "HomeNet"
    assert wifi["state"] == "connected"

    ports = parse_netstat_listening(
        "  Proto  Local Address          Foreign Address        State           PID\n"
        "  TCP    0.0.0.0:22             0.0.0.0:0              LISTENING       100\n"
        "  TCP    127.0.0.1:9222         0.0.0.0:0              LISTENING       200\n"
        "  UDP    0.0.0.0:5353           *:*                                    300\n"
    )
    assert ports["ok"] is True
    assert any(p["port"] == 22 for p in ports["listeners"])
    assert any(p["port"] == 9222 for p in ports["listeners"])


def test_ready_is_honest_and_lease_free():
    from exo_control.ops_catalog import get_op

    spec = get_op("ready")
    assert spec is not None
    assert spec.get("lease") is False
    body = _result({"op": "ready"})
    assert body["ok"] is True
    assert "whoami" in body["ready"]
    assert "hash" in body["ready"]
    assert "pilot" in body["ready"]
    assert "volume" in body["windows_native"]
    assert "lock_pc" in body["windows_native"]
    assert "wifi" in body["windows_native"]
    keyed = body["needs_key"]
    assert "search" in keyed
    assert "ok" in keyed["search"]
    if sys.platform != "win32":
        assert "volume" in body["windows_only"]
        assert body.get("on_windows") is False


def test_desk_ops_call_native_on_windows(monkeypatch):
    import exo_control.win_desk_ops as desk
    import exo_control.win_native as native

    monkeypatch.setattr(desk.sys, "platform", "win32")
    monkeypatch.setattr(desk, "_IMPL", None)
    monkeypatch.setattr(native, "volume", lambda step: {"ok": True, "level": 33, "native": True})
    monkeypatch.setattr(native, "recycle", lambda step: {"ok": True, "items": [], "native": True})
    monkeypatch.setattr(native, "tts", lambda step: {"ok": True, "spoke": True, "native": True})
    out = desk.volume({})
    assert out["ok"] is True and out.get("native") is True
    out = desk.recycle({"action": "list"})
    assert out["ok"] is True and out.get("native") is True
    out = desk.tts({"text": "hi"})
    assert out["ok"] is True and out.get("spoke") is True


def test_sys_ops_call_native_on_windows(monkeypatch):
    import exo_control.win_sys_ops as sysops
    import exo_control.sys_plus_ops as plus
    import exo_control.win_native as native

    monkeypatch.setattr(sysops.sys, "platform", "win32")
    monkeypatch.setattr(plus.sys, "platform", "win32")
    monkeypatch.setattr(sysops, "_IMPL", None)
    monkeypatch.setattr(plus, "_IMPL", None)
    monkeypatch.setattr(native, "wifi", lambda step: {"ok": True, "ssid": "X", "native": True})
    monkeypatch.setattr(native, "power", lambda step: {"ok": True, "percent": 70, "native": True})
    monkeypatch.setattr(native, "lock_pc", lambda step: {"ok": True, "locked": True, "native": True})
    monkeypatch.setattr(native, "dark_mode", lambda step: {"ok": True, "dark": True, "native": True})
    monkeypatch.setattr(native, "idle", lambda step: {"ok": True, "seconds": 1.5, "native": True})
    assert sysops.wifi({})["ssid"] == "X"
    assert sysops.power({"action": "status"})["percent"] == 70
    assert plus.lock_pc({"confirm": True})["locked"] is True
    assert plus.dark_mode({})["dark"] is True
    assert plus.idle({})["seconds"] == 1.5


def test_heal_attaches_glance(tmp_roots, monkeypatch):
    path = tmp_roots / "heal2.txt"
    eng = _engine()
    eng.ctrl.compact_observe = lambda **k: {
        "ok": True,
        "title": "Notepad",
        "a11y_labels": ["File", "Edit", "Save"],
    }
    denied = eng.execute([{"op": "files_write", "path": str(path), "text": "hi"}])
    assert denied["ok"] is False
    out = eng.execute([
        {"op": "lease_acquire", "agent_id": "n", "task": "heal", "ttl_sec": 20},
        {"op": "heal"},
        {"op": "lease_release"},
    ])
    assert out["ok"] is True
    heal = next(s["result"] for s in out["steps"] if s["op"] == "heal")
    assert heal["ok"] is True
    assert heal.get("glance", {}).get("title") == "Notepad"
    assert "Save" in (heal.get("glance", {}).get("labels") or [])
    assert path.read_text(encoding="utf-8") == "hi"


def test_aether_win_native_shim():
    import aether.win_native as shim
    import exo_control.win_native as impl
    assert shim.parse_netsh_wlan is impl.parse_netsh_wlan
