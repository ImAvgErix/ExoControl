"""2.1 human-substitute: aimed wheel dispatch, live eyes, catalog."""
from __future__ import annotations

import pytest

from aether.exec_engine import ExoExecEngine
from aether.ops_catalog import CORE_OPS, known_ops, lease_required_ops, list_ops
from aether.pointer import parse_scroll


class Hands:
    success = True
    message = "wheel notches=3 h=0 at=(400,300)"
    verified = True
    backend = "synthetic"
    target = None


class LiveStub:
    def __init__(self):
        self._focus_pid = 1
        self._focus_window_id = 10
        self._eyes = type("E", (), {"_running": False, "set_focus_hint": lambda *a, **k: None})()
        self.scroll_calls = []
        self.into_view_calls = []
        self.hover_calls = []
        self.eyes_started = 0
        self.eyes_stopped = 0

    def status(self):
        return {"ok": True}

    def smart_focus(self, title=None, pid=None, monitor=None):
        return {"ok": True, "pid": 1, "window_id": 10, "title": title or "X"}

    def smart_scroll(self, **kwargs):
        self.scroll_calls.append(kwargs)
        return Hands()

    def scroll_into_view(self, query=None, bbox=None, max_steps=12):
        self.into_view_calls.append({"query": query, "bbox": bbox, "max_steps": max_steps})
        return {"ok": True, "visible": True, "bbox": [10, 20, 30, 40], "steps": 2}

    def hover(self, query=None, x=None, y=None):
        self.hover_calls.append({"query": query, "x": x, "y": y})
        return Hands()

    def eyes_start(self, fps=6.0, ocr_on_change=True):
        self.eyes_started += 1
        self._eyes._running = True
        return {"ok": True, "fps": fps}

    def eyes_stop(self):
        self.eyes_stopped += 1
        self._eyes._running = False
        return {"ok": True, "stopped": True}

    def glance(self, force_ocr=False):
        return {
            "ok": True,
            "title": "Notepad",
            "changed": True,
            "age_ms": 4,
            "phash": "deadbeef",
            "labels": ["File", "Edit"],
            "pid": 1,
        }

    def smart_click(self, **kwargs):
        return Hands()


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("EXO_LOCK_DIR", str(tmp_path / "locks"))
    monkeypatch.setenv("EXO_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("EXO_FILE_ROOTS", str(tmp_path / "workspace"))
    monkeypatch.setenv("EXO_LIVE_EYES", "1")
    (tmp_path / "workspace").mkdir()
    yield tmp_path


def test_catalog_has_human_ops():
    names = known_ops()
    for op in (
        "scroll", "scroll_into_view", "hover",
        "eyes_read", "look", "glance",
        "browser_scroll_into_view", "browser_hover",
    ):
        assert op in names
    req = lease_required_ops()
    assert "scroll" in req
    assert "scroll_into_view" in req
    assert "hover" in req
    assert "browser_scroll" in req
    compact = list_ops()
    ops = {row["op"] for row in compact["ops"]}
    assert "scroll" in ops
    assert "scroll_into_view" in ops
    assert "hover" in ops
    assert compact["count"] == len(CORE_OPS)
    purpose = next(e["purpose"] for e in list_ops(query="scroll", detail=True)["ops"] if e["op"] == "scroll")
    assert "Home" in purpose or "never" in purpose.lower()


def test_scroll_dispatch_passes_notches(home):
    stub = LiveStub()
    eng = ExoExecEngine(controller=stub)
    out = eng.execute([
        {"op": "lease_acquire", "agent_id": "h", "task": "wheel", "ttl_sec": 30},
        {"op": "scroll", "notches": 4, "direction": "down"},
        {"op": "scroll_into_view", "query": "Save"},
        {"op": "hover", "query": "File"},
        {"op": "lease_release"},
    ])
    assert out["ok"] is True, out.get("last_error") or out
    assert stub.scroll_calls
    assert stub.scroll_calls[0].get("notches") == 4
    assert stub.into_view_calls[0]["query"] == "Save"
    assert stub.hover_calls[0]["query"] == "File"


def test_lease_starts_eyes_and_hands_attach_seen(home):
    stub = LiveStub()
    eng = ExoExecEngine(controller=stub)
    out = eng.execute([
        {"op": "lease_acquire", "agent_id": "h", "task": "look", "ttl_sec": 30},
        {"op": "scroll", "notches": 2},
        {"op": "lease_release"},
    ])
    assert out["ok"] is True, out.get("last_error") or out
    acq = next(s for s in out["steps"] if s["op"] == "lease_acquire")
    assert acq["result"].get("eyes", {}).get("ok") is True
    assert stub.eyes_started >= 1
    scroll = next(s for s in out["steps"] if s["op"] == "scroll")
    seen = scroll["result"].get("seen")
    assert seen and seen.get("title") == "Notepad"
    assert "File" in seen.get("labels", [])
    rel = next(s for s in out["steps"] if s["op"] == "lease_release")
    assert stub.eyes_stopped >= 1
    assert rel["result"].get("eyes", {}).get("stopped") is True


def test_seen_false_skips_glance(home):
    stub = LiveStub()
    eng = ExoExecEngine(controller=stub)
    out = eng.execute([
        {"op": "lease_acquire", "agent_id": "h", "task": "quiet", "ttl_sec": 30},
        {"op": "scroll", "notches": 1, "seen": False},
        {"op": "lease_release"},
    ])
    scroll = next(s for s in out["steps"] if s["op"] == "scroll")
    assert "seen" not in scroll["result"]


def test_eyes_false_on_lease_skips_loop(home):
    stub = LiveStub()
    eng = ExoExecEngine(controller=stub)
    out = eng.execute([
        {"op": "lease_acquire", "agent_id": "h", "task": "noeyes", "ttl_sec": 30, "eyes": False},
        {"op": "lease_release"},
    ])
    assert out["ok"] is True
    assert stub.eyes_started == 0
    acq = next(s for s in out["steps"] if s["op"] == "lease_acquire")
    assert "eyes" not in acq["result"]


def test_scroll_requires_focus(home):
    stub = LiveStub()
    stub._focus_pid = None
    stub._focus_window_id = None
    eng = ExoExecEngine(controller=stub)
    out = eng.execute([
        {"op": "lease_acquire", "agent_id": "h", "task": "nofocus", "ttl_sec": 30, "eyes": False},
        {"op": "scroll", "notches": 1},
        {"op": "lease_release"},
    ])
    assert out["ok"] is False
    err = (out.get("last_error") or {}).get("error") or ""
    assert "focus" in err


def test_parse_scroll_default_is_not_end_home():
    req = parse_scroll({"direction": "down", "amount": "page"})
    assert req["notches"] > 0
    assert req["notches"] < 40
