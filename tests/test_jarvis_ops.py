from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from aether import desktop_lease
from aether.exec_engine import AetherExecEngine
from aether.smart import SmartController


@pytest.fixture
def lease_home(tmp_path, monkeypatch):
    monkeypatch.setenv("AETHER_LOCK_DIR", str(tmp_path / "locks"))
    monkeypatch.setenv("AETHER_STATE_DIR", str(tmp_path / "state"))
    yield tmp_path


class JarvisStub(SmartController):
    def __init__(self):
        self._focus_pid = 1
        self._focus_window_id = 10
        self._metrics = {}
        self.window_calls = []

        class _Macros:
            def is_recording(self):
                return False

            def add(self, *a, **k):
                pass

        class _Perc:
            def capture(self, monitor=1, region=None):
                from PIL import Image

                return Image.new("RGB", (20, 10), color=(1, 2, 3))

        self.macros = _Macros()
        self.perception = _Perc()

    def status(self):
        return {"ok": True}

    def smart_focus(self, title=None, pid=None):
        return {"ok": True, "pid": 1, "window_id": 10, "title": title or "X", "raised": True}

    def focus_window(self, pid, window_id=None):
        if isinstance(pid, str):
            return self.smart_focus(title=pid)
        self._focus_pid = pid
        self._focus_window_id = window_id or 10
        return {"ok": True, "pid": pid, "window_id": self._focus_window_id, "raised": True}

    def window_state(self, window_id):
        return {"known": True, "rect": [0, 0, 20, 10], "visible": True}

    def window_min(self, hwnd=None):
        self.window_calls.append(("min", hwnd))
        return {"ok": True, "action": "min", "window_id": hwnd or self._focus_window_id}

    def window_max(self, hwnd=None):
        self.window_calls.append(("max", hwnd))
        return {"ok": True, "action": "max", "window_id": hwnd or self._focus_window_id}

    def window_restore(self, hwnd=None):
        self.window_calls.append(("restore", hwnd))
        return {"ok": True, "action": "restore", "window_id": hwnd or self._focus_window_id}

    def window_close(self, hwnd=None):
        self.window_calls.append(("close", hwnd))
        return {"ok": True, "action": "close", "window_id": hwnd or self._focus_window_id}

    def smart_hotkey(self, keys):
        class R:
            success = True
            message = f"hotkey {keys}"
            verified = True
            backend = "stub"
            attempts = 1
            from_memory = False
            target = None

        self.last_keys = keys
        return R()

    def clipboard_get(self):
        return {"ok": True, "text": "x"}

    def compact_observe(self, include_ocr=True, max_ocr=40, max_elements=30):
        return {"ok": True, "a11y_labels": ["A"], "ocr": [], "include_ocr": include_ocr}


def test_lease_acquire_conflict_expire_release(lease_home):
    a = desktop_lease.acquire("agent-a", task="one", ttl_sec=2)
    assert a["ok"] is True
    token = a["token"]

    b = desktop_lease.acquire("agent-b", task="two", ttl_sec=2)
    assert b["ok"] is False
    assert b["holder"] == "agent-a"

    st = desktop_lease.status()
    assert st["held"] is True
    assert st["token"] == token

    renewed = desktop_lease.renew(token, ttl_sec=1)
    assert renewed["ok"] is True

    time.sleep(1.1)
    stolen = desktop_lease.acquire("agent-b", task="steal", ttl_sec=5)
    assert stolen["ok"] is True
    assert stolen["token"] != token

    rel = desktop_lease.release(stolen["token"])
    assert rel["ok"] is True
    assert desktop_lease.status()["held"] is False


def test_mutating_ops_require_lease(lease_home):
    eng = AetherExecEngine(controller=JarvisStub())
    denied = eng.execute([{"op": "keys", "keys": "ctrl+l"}])
    assert denied["ok"] is False
    assert denied["steps"][0]["result"]["error"] == "desktop lease required"

    ok = eng.execute(
        [
            {"op": "lease_acquire", "agent_id": "t", "task": "keys", "ttl_sec": 30},
            {"op": "keys", "keys": "ctrl+l"},
            {"op": "lease_release"},
        ]
    )
    assert ok["ok"] is True
    assert eng.ctrl.last_keys == ["ctrl", "l"]


def test_readonly_ops_no_lease(lease_home, monkeypatch):
    eng = AetherExecEngine(controller=JarvisStub())
    monkeypatch.setenv("AETHER_FILE_ROOTS", str(lease_home))
    monkeypatch.setattr(
        "aether.exo_bridge.discover_cdp_endpoints",
        lambda extra_ports=None: [{"port": 9229, "endpoint": "http://127.0.0.1:9229", "browser": "stub", "targets": []}],
    )
    result = eng.execute(
        [
            {"op": "cdp_discover"},
            {"op": "eyes"},
            {"op": "files_list", "path": str(lease_home)},
            {"op": "lease_status"},
        ]
    )
    assert result["ok"] is True
    assert result["steps"][1]["result"]["cdp"]["count"] == 1


def test_wait_cdp_stub(lease_home, monkeypatch):
    calls = {"n": 0}

    def fake(extra_ports=None):
        calls["n"] += 1
        if calls["n"] < 3:
            return []
        return [{"port": 9229, "endpoint": "http://127.0.0.1:9229", "browser": "x", "targets": []}]

    monkeypatch.setattr("aether.exo_bridge.discover_cdp_endpoints", fake)
    eng = AetherExecEngine(controller=JarvisStub())
    result = eng.execute([{"op": "wait_cdp", "timeout": 5, "poll": 0.01, "port": 9229}])
    assert result["ok"] is True
    assert result["steps"][0]["result"]["count"] == 1


def test_eyes_stub(lease_home, monkeypatch):
    monkeypatch.setattr(
        "aether.exo_bridge.discover_cdp_endpoints",
        lambda extra_ports=None: [{"port": 9333, "endpoint": "http://127.0.0.1:9333", "browser": "Edge", "targets": [1]}],
    )
    eng = AetherExecEngine(controller=JarvisStub())
    out = eng.execute([{"op": "eyes"}])["steps"][0]["result"]
    assert out["ok"] is True
    assert out["observe"]["a11y_labels"] == ["A"]
    assert out["cdp"]["endpoints"][0]["port"] == 9333


def test_focus_window_accepts_title_string():
    c = JarvisStub()
    assert c.focus_window("Exo Launcher")["ok"] is True


def test_screenshot_path_and_cdp_ops(tmp_path, lease_home, monkeypatch):
    monkeypatch.setattr(
        "aether.exo_bridge.discover_cdp_endpoints",
        lambda extra_ports=None: [{"port": 9229, "endpoint": "http://127.0.0.1:9229", "browser": "stub", "targets": []}],
    )
    eng = AetherExecEngine(controller=JarvisStub())
    out = str(tmp_path / "jarvis-shot-test.png")
    result = eng.execute(
        [
            {"op": "lease_acquire", "agent_id": "jarvis", "task": "shot", "ttl_sec": 60},
            {"op": "shot", "path": out, "title": "Exo Launcher"},
            {"op": "cdp_discover"},
            {"op": "keys", "keys": "ctrl+l"},
            {"op": "lease_release"},
        ]
    )
    assert result["ok"] is True
    assert Path(out).is_file()
    assert eng.ctrl.last_keys == ["ctrl", "l"]


def test_window_ops_dispatch_to_controller(lease_home):
    stub = JarvisStub()
    eng = AetherExecEngine(controller=stub)
    result = eng.execute(
        [
            {"op": "lease_acquire", "agent_id": "w", "task": "win", "ttl_sec": 30},
            {"op": "window_min"},
            {"op": "window_max"},
            {"op": "window_restore"},
            {"op": "window_close"},
            {"op": "window", "action": "min"},
            {"op": "lease_release"},
        ]
    )
    assert result["ok"] is True
    assert [c[0] for c in stub.window_calls] == ["min", "max", "restore", "close", "min"]


def test_launch_op_uses_popen(lease_home, monkeypatch):
    stub = JarvisStub()
    eng = AetherExecEngine(controller=stub)
    fake = MagicMock()
    fake.pid = 4321
    monkeypatch.setattr("subprocess.Popen", MagicMock(return_value=fake))
    result = eng.execute(
        [
            {"op": "lease_acquire", "agent_id": "l", "task": "launch", "ttl_sec": 30},
            {
                "op": "launch",
                "command": r"C:\Tools\demo.exe",
                "args": ["--flag"],
                "cwd": r"C:\Tools",
                "env": {"FOO": "bar"},
            },
            {"op": "lease_release"},
        ]
    )
    assert result["ok"] is True
    assert result["steps"][1]["result"]["pid"] == 4321


def test_apps_and_files_list(lease_home, monkeypatch):
    monkeypatch.setenv("AETHER_FILE_ROOTS", str(lease_home))
    monkeypatch.setattr(
        "aether.exec_engine._list_apps",
        lambda max_items=80: {"ok": True, "apps": [{"pid": 1, "title": "Demo", "exe": r"C:\Demo.exe", "hwnd": 9}], "count": 1},
    )
    eng = AetherExecEngine(controller=JarvisStub())
    result = eng.execute(
        [
            {"op": "apps"},
            {"op": "files_list", "path": str(lease_home), "max": 10},
            {"op": "proc", "action": "list"},
        ]
    )
    assert result["ok"] is True
    assert result["steps"][0]["result"]["apps"][0]["title"] == "Demo"
    assert result["steps"][1]["result"]["ok"] is True


def test_proc_kill_requires_confirm(lease_home, monkeypatch):
    eng = AetherExecEngine(controller=JarvisStub())
    denied = eng.execute(
        [
            {"op": "lease_acquire", "agent_id": "p", "task": "kill", "ttl_sec": 30},
            {"op": "proc", "action": "kill", "pid": 1},
        ]
    )
    assert denied["steps"][1]["result"]["ok"] is False
    assert "confirm" in denied["steps"][1]["result"]["error"]

    st = desktop_lease.status()
    if st.get("token"):
        desktop_lease.release(st["token"])

    monkeypatch.setattr(
        "aether.exec_engine._kill_proc",
        lambda pid: {"ok": True, "pid": pid},
    )
    ok = eng.execute(
        [
            {"op": "lease_acquire", "agent_id": "p2", "task": "kill2", "ttl_sec": 30},
            {"op": "proc", "action": "kill", "pid": 99, "confirm": True},
            {"op": "lease_release"},
        ]
    )
    assert ok["ok"] is True
    assert ok["steps"][1]["result"]["pid"] == 99


def test_notify_stubs_subprocess(lease_home, monkeypatch):
    monkeypatch.setenv("AETHER_NOTIFY_STUB", "1")
    eng = AetherExecEngine(controller=JarvisStub())
    # Explicit stub still works; env stub only honored under pytest.
    result = eng.execute([{"op": "notify", "title": "Aether", "message": "hello", "stub": True}])
    assert result["ok"] is True
    assert result["steps"][0]["result"].get("stub") is True
    # env alone must NOT stub anymore (live prove safety)


def test_clipboard_image_save(tmp_path, lease_home, monkeypatch):
    from PIL import Image

    img = Image.new("RGB", (4, 4), color=(9, 8, 7))
    monkeypatch.setattr("PIL.ImageGrab.grabclipboard", lambda: img)
    out = tmp_path / "clip.png"
    eng = AetherExecEngine(controller=JarvisStub())
    result = eng.execute([{"op": "clipboard_image_save", "path": str(out)}])
    assert result["ok"] is True
    assert out.is_file()


def test_desktop_unsupported_without_pyvda(lease_home, monkeypatch):
    import builtins

    real_import = builtins.__import__

    def guarded(name, *a, **k):
        if name == "pyvda":
            raise ImportError("no pyvda")
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", guarded)
    eng = AetherExecEngine(controller=JarvisStub())
    result = eng.execute([{"op": "desktop", "action": "list"}])
    assert result["steps"][0]["result"]["ok"] is False
    assert result["steps"][0]["result"]["error"] == "unsupported"


def test_persist_last_focus(lease_home):
    desktop_lease.persist_last_focus({"pid": 5, "window_id": 6, "title": "T"})
    loaded = desktop_lease.load_last_focus()
    assert loaded["pid"] == 5
    assert loaded["title"] == "T"
