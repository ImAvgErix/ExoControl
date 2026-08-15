"""Live seat — hold the desk like remote access, then drive real HID."""
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


@pytest.fixture
def hid(monkeypatch):
    from exo_control import session_ops

    log: list = []

    def impl(kind, payload):
        log.append((kind, dict(payload)))
        if kind == "pos":
            return {"ok": True, "x": int(payload.get("x") or 0), "y": int(payload.get("y") or 0)}
        return {"ok": True, "kind": kind}

    monkeypatch.setattr(session_ops, "_IMPL", impl)
    return log


def _engine():
    from exo_control.exec_engine import ExoExecEngine

    return ExoExecEngine()


def _result(script, eng=None):
    out = (eng or _engine()).execute(script if isinstance(script, list) else [script])
    return out


def _body(script, eng=None, index=0):
    return _result(script, eng)["steps"][index]["result"]


def test_session_catalog_and_aliases():
    from exo_control.addon_ops import ROUTES
    from exo_control.ops_catalog import get_op, known_ops

    free = {
        "session_open": "session_open",
        "seat": "session_open",
        "take_seat": "session_open",
        "session_close": "session_close",
        "leave_seat": "session_close",
        "session_end": "session_close",
        "session_status": "session_status",
        "seat_status": "session_status",
    }
    hands = ("pointer", "mouse", "keypress", "drive")
    for name, canon in free.items():
        spec = get_op(name)
        assert spec is not None, name
        assert spec["op"] == canon
        assert spec.get("lease") is False
        assert name in known_ops()
        assert name not in ROUTES
    for name in hands:
        spec = get_op(name)
        assert spec is not None, name
        assert spec.get("lease") is True
        assert name not in ROUTES


def test_session_open_requires_agent(tmp_roots):
    body = _body({"op": "session_open", "task": "remote"})
    assert body["ok"] is False
    assert "agent" in (body.get("error") or "").lower()
    assert "token" not in body


def test_take_seat_hides_token_and_holds_across_scripts(tmp_roots, hid):
    eng = _engine()
    opened = _body(
        {"op": "seat", "agent_id": "remote-friend", "task": "use my pc", "ttl_sec": 90},
        eng,
    )
    assert opened["ok"] is True
    assert opened["seated"] is True
    assert opened["held"] is True
    assert opened["holder"] == "remote-friend"
    assert opened["task"] == "use my pc"
    assert "token" not in opened
    assert "token" not in str(opened).lower().replace("ttl_sec", "")

    later = _result(
        [
            {"op": "session_status"},
            {"op": "pointer", "x": 120, "y": 80, "human": False},
            {"op": "mouse", "action": "click", "button": "left"},
            {"op": "keypress", "key": "enter"},
        ],
        eng,
    )
    assert later["ok"] is True
    status = later["steps"][0]["result"]
    assert status["seated"] is True
    assert status["holder"] == "remote-friend"
    assert "token" not in status
    assert hid[0][0] == "move"
    assert hid[0][1]["x"] == 120 and hid[0][1]["y"] == 80
    assert hid[1][0] == "click"
    assert hid[2][0] == "key"


def test_drive_burst_and_failed_hand_keeps_seat(tmp_roots, hid):
    eng = _engine()
    out = _result(
        [
            {"op": "take_seat", "agent_id": "driver", "task": "burst", "ttl_sec": 60},
            {
                "op": "drive",
                "events": [
                    {"move": [10, 20]},
                    {"click": "right"},
                    {"type": "hello"},
                    {"key": "enter"},
                    {"wheel": 2},
                ],
            },
            {"op": "pointer", "x": "nope", "y": 1},
        ],
        eng,
    )
    assert out["ok"] is False
    drive = next(s["result"] for s in out["steps"] if s["op"] == "drive")
    assert drive["ok"] is True
    assert drive["count"] == 5
    kinds = [k for k, _ in hid]
    assert kinds == ["move", "click", "type", "key", "wheel"]
    assert hid[2][1]["text"] == "hello"
    status = _body({"op": "seat_status"}, eng)
    assert status["seated"] is True
    assert status["held"] is True


def test_pointer_needs_lease_without_seat(tmp_roots, hid):
    denied = _body({"op": "pointer", "x": 1, "y": 1})
    assert denied["ok"] is False
    assert "lease" in (denied.get("error") or "").lower()
    assert hid == []


def test_leave_seat_releases_and_blocks_hands(tmp_roots, hid):
    eng = _engine()
    _result({"op": "session_open", "agent_id": "guest", "task": "visit", "ttl_sec": 40}, eng)
    closed = _body({"op": "leave_seat"}, eng)
    assert closed["ok"] is True
    assert closed["seated"] is False
    assert closed.get("released") is True
    assert "token" not in closed
    status = _body({"op": "session_status"}, eng)
    assert status["seated"] is False
    assert status.get("held") is False
    denied = _body({"op": "mouse", "action": "click"}, eng)
    assert denied["ok"] is False
    assert "lease" in (denied.get("error") or "").lower()


def test_foreign_seat_conflict_hides_token(tmp_roots):
    a = _engine()
    b = _engine()
    first = _body({"op": "session_open", "agent_id": "alice", "task": "desk", "ttl_sec": 40}, a)
    assert first["ok"] is True
    clash = _body({"op": "session_open", "agent_id": "bob", "task": "steal", "ttl_sec": 40}, b)
    assert clash["ok"] is False
    assert clash.get("holder") == "alice"
    assert "token" not in clash
    assert "token" not in str(clash)


def test_raw_hid_without_hook_is_windows_only(tmp_roots, monkeypatch):
    from exo_control import session_ops

    monkeypatch.setattr(session_ops, "_IMPL", None)
    monkeypatch.setattr(session_ops.sys, "platform", "linux")
    eng = _engine()
    _result({"op": "session_open", "agent_id": "x", "task": "hid", "ttl_sec": 20}, eng)
    body = _body({"op": "pointer", "x": 4, "y": 5, "human": False}, eng)
    assert body["ok"] is False
    assert body.get("code") == "WINDOWS_ONLY"


def test_ready_lists_live_seat(tmp_roots):
    body = _body({"op": "ready"})
    assert body["ok"] is True
    assert "session" in body["ready"] or "session_open" in body["ready"]


def test_aether_session_shim():
    import aether.session_ops as shim
    import exo_control.session_ops as impl

    assert shim.public_status is impl.public_status
