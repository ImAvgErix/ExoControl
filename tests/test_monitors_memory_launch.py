"""P1: multi-monitor bind, persistent UI memory, Start Menu fuzzy launch."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

from aether.monitors import (
    filter_windows_for_monitor,
    list_monitor_dicts,
    monitor_bind_error,
    rect_on_monitor,
    window_on_monitor,
)
from aether.memory import UIMemory, MemoryHit
from aether.launch_resolve import resolve_launch_target, _fuzzy_score
from aether.smart import SmartController, Target, ActionOutcome
from aether.exec_engine import AetherExecEngine


@pytest.fixture
def state_home(tmp_path, monkeypatch):
    monkeypatch.setenv("AETHER_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("AETHER_LOCK_DIR", str(tmp_path / "locks"))
    yield tmp_path


# ── Multi-monitor ────────────────────────────────────────────────────


def test_rect_on_monitor_center_and_overlap():
    mon = {"id": 1, "left": 0, "top": 0, "width": 1920, "height": 1080, "right": 1920, "bottom": 1080}
    mon2 = {"id": 2, "left": 1920, "top": 0, "width": 1920, "height": 1080, "right": 3840, "bottom": 1080}
    assert rect_on_monitor([100, 100, 500, 400], mon) is True
    assert rect_on_monitor([100, 100, 500, 400], mon2) is False
    assert rect_on_monitor([2000, 100, 2800, 800], mon2) is True
    # mostly on mon2
    assert rect_on_monitor([1800, 100, 3000, 800], mon2, require_center=True) is True


def test_filter_windows_for_monitor(monkeypatch):
    wins = [
        {"title": "A", "pid": 1, "handle": 10, "rect": [100, 100, 800, 600]},
        {"title": "B", "pid": 2, "handle": 20, "rect": [2000, 100, 2800, 700]},
        {"title": "C", "pid": 3, "handle": 30, "rect": [50, 50, 200, 200]},
    ]

    def fake_list():
        return [
            {"id": 1, "left": 0, "top": 0, "width": 1920, "height": 1080, "right": 1920, "bottom": 1080},
            {"id": 2, "left": 1920, "top": 0, "width": 1920, "height": 1080, "right": 3840, "bottom": 1080},
        ]

    monkeypatch.setattr("aether.monitors.list_monitor_dicts", fake_list)
    hits, mon = filter_windows_for_monitor(wins, 2)
    assert mon is not None
    assert mon["id"] == 2
    titles = {w["title"] for w in hits}
    assert titles == {"B"}
    empty, bad = filter_windows_for_monitor(wins, 99)
    assert empty == []
    assert bad is None


def test_smart_focus_monitor_bind_fail_closed(monkeypatch):
    c = SmartController.__new__(SmartController)
    c._focus_pid = None
    c._focus_window_id = None
    c._focus_monitor = None
    c._focus_rect = None
    c.macros = type("M", (), {"is_recording": lambda self: False})()
    c.list_windows = lambda: [
        {"title": "Exo Launcher", "pid": 100, "handle": 1, "class_name": "WinUIWindow",
         "visible": True, "minimized": False, "rect": [100, 100, 900, 700]},
    ]
    c.focus_window = lambda pid, wid=None: {"ok": True, "raised": True, "pid": pid, "window_id": wid}

    monkeypatch.setattr(
        "aether.monitors.list_monitor_dicts",
        lambda: [
            {"id": 1, "left": 0, "top": 0, "width": 1920, "height": 1080, "right": 1920, "bottom": 1080},
            {"id": 2, "left": 1920, "top": 0, "width": 1920, "height": 1080, "right": 3840, "bottom": 1080},
        ],
    )
    c.smart_focus = SmartController.smart_focus.__get__(c, SmartController)

    ok = c.smart_focus(title="Exo", monitor=1)
    assert ok["ok"] is True
    assert ok["monitor"] == 1

    bad = c.smart_focus(title="Exo", monitor=2)
    assert bad["ok"] is False
    assert "monitor" in (bad.get("error") or "").lower() or bad.get("monitor") == 2

    unknown = c.smart_focus(title="Exo", monitor=9)
    assert unknown["ok"] is False


def test_exec_focus_passes_monitor(state_home, monkeypatch):
    seen = {}

    class Ctrl:
        def list_windows(self, monitor=None):
            return []

        def smart_focus(self, title=None, pid=None, monitor=None):
            seen["monitor"] = monitor
            seen["title"] = title
            return {"ok": True, "pid": 1, "window_id": 2, "title": title, "monitor": monitor}

        def read_ui(self, **kw):
            return {"elements": [], "labels": [], "pid": 1, "title": "t"}

        def compact_observe(self, include_ocr=False, monitor=None, **kw):
            seen["obs_monitor"] = monitor
            return {"a11y": [], "monitor": monitor, "elapsed": 0.01}

    eng = AetherExecEngine(controller=Ctrl())
    r = eng.execute([
        {"op": "lease_acquire", "agent_id": "m", "task": "mon", "ttl_sec": 30},
        {"op": "focus", "title": "Exo", "monitor": 2},
        {"op": "observe", "monitor": 2},
    ])
    assert r["ok"] is True, r
    assert seen.get("monitor") == 2
    assert seen.get("obs_monitor") == 2


def test_screenshot_wrong_monitor_fails(state_home, monkeypatch):
    class Ctrl:
        _focus_window_id = 1
        perception = type("P", (), {"capture": staticmethod(lambda **k: None)})()

        def smart_focus(self, title=None, pid=None, monitor=None):
            return {
                "ok": True,
                "pid": 1,
                "window_id": 1,
                "title": "Exo Launcher",
                "rect": [100, 100, 800, 600],
            }

        def window_state(self, wid=None):
            return {"known": True, "title": "Exo Launcher", "rect": [100, 100, 800, 600], "window_id": 1}

        def list_windows(self):
            return []

    monkeypatch.setattr(
        "aether.monitors.list_monitor_dicts",
        lambda: [
            {"id": 1, "left": 0, "top": 0, "width": 1920, "height": 1080, "right": 1920, "bottom": 1080},
            {"id": 2, "left": 1920, "top": 0, "width": 1920, "height": 1080, "right": 3840, "bottom": 1080},
        ],
    )
    eng = AetherExecEngine(controller=Ctrl())
    r = eng.execute([
        {"op": "lease_acquire", "agent_id": "s", "task": "shot", "ttl_sec": 30},
        {"op": "screenshot", "title": "Exo", "monitor": 2},
    ])
    # should fail closed (wrong monitor or capture fail after bind)
    step = r["steps"][-1]["result"]
    assert step.get("ok") is False
    err = (step.get("error") or "").lower()
    assert "monitor" in err or "capture" in err or "window" in err


# ── Persistent UI memory ─────────────────────────────────────────────


def test_memory_persists_across_instances(state_home):
    path = state_home / "state" / "ui_memory.json"
    m1 = UIMemory(path=path, persist=True)
    m1.record_success(
        "Settings",
        {
            "label": "Settings",
            "kind": "a11y",
            "x": 10,
            "y": 20,
            "bbox": [0, 0, 40, 40],
            "pid": 111,
            "process_name": "exolauncher",
            "element_index": 3,
        },
    )
    assert path.is_file()
    m2 = UIMemory(path=path, persist=True)
    hit = m2.lookup("Settings", process_name="exolauncher")
    assert hit is not None
    assert hit.label == "Settings"
    assert hit.process_name == "exolauncher"
    assert hit.element_index == 3
    # PID recycle: still find by process name
    hit2 = m2.lookup("Settings", pid=99999, process_name="exolauncher")
    assert hit2 is not None


def test_memory_invalidate_on_miss(state_home):
    path = state_home / "state" / "ui_memory.json"
    m = UIMemory(path=path, persist=True)
    m.record_success(
        "Settings",
        {"label": "Settings", "kind": "a11y", "x": 1, "y": 2, "process_name": "exolauncher"},
    )
    assert m.lookup("Settings", process_name="exolauncher") is not None
    removed = m.invalidate("Settings")
    assert removed >= 1
    assert m.lookup("Settings", process_name="exolauncher") is None


def test_smart_click_invalidates_memory_on_miss(state_home, monkeypatch):
    path = state_home / "state" / "ui_memory.json"
    mem = UIMemory(path=path, persist=True)
    mem.record_success(
        "GhostBtn",
        {
            "label": "GhostBtn",
            "kind": "a11y",
            "x": 5,
            "y": 5,
            "bbox": [0, 0, 10, 10],
            "pid": 42,
            "process_name": "app",
            "element_index": 1,
        },
    )

    c = SmartController.__new__(SmartController)
    c.memory = mem
    c._focus_pid = 42
    c._focus_window_id = 1
    c._focus_monitor = None
    c._focus_rect = None
    c._metrics = {"clicks": 0, "memory_hits": 0}
    c._timings = {}
    c._safety_prechecked = True
    c.max_retries = 0
    c.verify = False
    c.similarity_threshold = 0.1
    c.backend = type("B", (), {"name": "stub"})()
    c.macros = type("M", (), {"is_recording": lambda self: False, "add": lambda *a, **k: None})()
    c.log = type("L", (), {"record": lambda *a, **k: None})()
    c.safety = type("S", (), {"check": lambda *a, **k: (True, "")})()
    c._focus_process_name = lambda: "app"
    c.find_targets = lambda query, obs=None, allow_ocr=True, **kw: [
        Target(kind="memory", label="GhostBtn", x=5, y=5, confidence=0.9, source="memory",
               pid=42, element_index=1)
    ]
    c._deliver_click = lambda **kw: type("D", (), {"ok": False, "backend": "stub", "message": "miss"})()
    c.ui_hash = lambda force=False: "h"
    c.observe = lambda **kw: {}
    c._verify_change = lambda a, b: False
    c._record_stat = lambda *a, **k: None
    c.smart_click = SmartController.smart_click.__get__(c, SmartController)

    out = c.smart_click(query="GhostBtn")
    assert out.success is False
    assert mem.lookup("GhostBtn", process_name="app") is None


# ── Fuzzy launch / Start Menu ────────────────────────────────────────


def test_fuzzy_score_ranks():
    assert _fuzzy_score("notepad", "Notepad") == 1.0
    assert _fuzzy_score("chrome", "Google Chrome") >= 0.55
    assert _fuzzy_score("zzz", "Notepad") < 0.55


def test_notepad_and_unknown():
    assert resolve_launch_target(app="notepad").get("ok") is True
    assert resolve_launch_target(app="definitely_not_an_app_zzzx").get("ok") is False


def test_start_menu_scan_finds_lnk(tmp_path, monkeypatch):
    root = tmp_path / "Microsoft" / "Windows" / "Start Menu" / "Programs"
    root.mkdir(parents=True)
    lnk = root / "Cool App.lnk"
    lnk.write_bytes(b"dummy")  # resolve will fall back to lnk path itself
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setenv("PROGRAMDATA", str(tmp_path / "empty_pd"))
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    (tmp_path / "empty_pd").mkdir(exist_ok=True)

    # Force miss on which/aliases so Start Menu path is exercised
    monkeypatch.setattr("aether.launch_resolve.shutil.which", lambda *a, **k: None)
    # Avoid alias shell_execute for unknown key
    out = resolve_launch_target(app="Cool App")
    assert out.get("ok") is True, out
    assert out.get("method") in {"start_menu", "start_menu_lnk"}
    assert "Cool" in (out.get("matched") or "")


def test_launch_default_wait_ready(state_home, monkeypatch):
    """Fuzzy app launch should wait for window unless wait_ready=false."""
    waits = []

    class Ctrl:
        def list_windows(self):
            return [{"title": "Untitled - Notepad", "pid": 555, "handle": 9}]

    def fake_resolve(*a, **k):
        return {"ok": True, "command": "notepad.exe", "method": "alias_which", "app": "notepad"}

    def fake_popen(*a, **k):
        class P:
            pid = 555
        return P()

    def fake_wait(ctrl, step):
        waits.append(step)
        return {"ok": True, "pid": 555, "title": "Untitled - Notepad"}

    monkeypatch.setattr("aether.launch_resolve.resolve_launch_target", fake_resolve)
    monkeypatch.setattr("subprocess.Popen", fake_popen)
    monkeypatch.setattr("aether.exec_engine._wait_window", fake_wait)
    monkeypatch.setattr("aether.exec_engine.resolve_launch_target", fake_resolve, raising=False)

    # Patch where launch imports it
    import aether.launch_resolve as lr
    monkeypatch.setattr(lr, "resolve_launch_target", fake_resolve)

    eng = AetherExecEngine(controller=Ctrl())
    # Re-bind _run_step path: launch imports resolve inside function
    import aether.exec_engine as ee
    monkeypatch.setattr(ee, "_wait_window", fake_wait)

    r = eng.execute([
        {"op": "lease_acquire", "agent_id": "l", "task": "launch", "ttl_sec": 30},
        {"op": "launch", "app": "notepad"},
    ])
    assert r["ok"] is True, r
    assert waits, "expected wait_window for fuzzy app launch"
    assert "notepad" in str(waits[0].get("title_contains") or "").lower() or waits[0].get("pid") == 555
