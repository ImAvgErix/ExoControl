
"""Live-prove fixes: notify stub gate, browser timeout seconds, dead-target waits, aria resolve."""
from __future__ import annotations

import asyncio
import time
from typing import Any, Dict, List, Optional

import pytest

from aether.exec_engine import AetherExecEngine, _notify_toast
from aether.smart import SmartController, ActionOutcome
from aether.launch_resolve import resolve_launch_target


@pytest.fixture
def lease_home(tmp_path, monkeypatch):
    monkeypatch.setenv("AETHER_LOCK_DIR", str(tmp_path / "locks"))
    monkeypatch.setenv("AETHER_STATE_DIR", str(tmp_path / "state"))
    yield tmp_path


def test_notify_env_stub_ignored_live_default(monkeypatch, lease_home):
    """AETHER_NOTIFY_STUB=1 must NOT stub; only step stub:true does."""
    monkeypatch.setenv("AETHER_NOTIFY_STUB", "1")
    calls = []

    def fake_toast(title, body):
        calls.append((title, body))
        return {"ok": True, "title": title, "body": body, "queued": True, "method": "notifyicon", "stub": False}

    monkeypatch.setattr("aether.exec_engine._notify_toast", fake_toast)
    eng = AetherExecEngine(controller=type("C", (), {"list_windows": lambda self: []})())
    live = eng.execute([
        {"op": "lease_acquire", "agent_id": "n", "task": "toast", "ttl_sec": 20},
        {"op": "notify", "title": "Live", "body": "toast"},
        {"op": "lease_release"},
    ])
    assert live["ok"] is True
    assert live["steps"][1]["result"].get("stub") is False
    assert calls and calls[0][0] == "Live"
    stub = eng.execute([
        {"op": "lease_acquire", "agent_id": "n2", "task": "toast2", "ttl_sec": 20},
        {"op": "notify", "title": "X", "body": "Y", "stub": True},
        {"op": "lease_release"},
    ])
    assert stub["steps"][1]["result"].get("stub") is True


def test_browser_wait_timeout_seconds(monkeypatch, lease_home):
    seen = {}

    class FakeBrowser:
        def wait_for(self, text=None, selector=None, timeout=15000, space_id=None, name=None, query=None):
            seen["timeout"] = timeout
            return {"ok": True, "method": "text", "text": text}

    eng = AetherExecEngine(controller=type("C", (), {"list_windows": lambda self: []})())
    eng._browser = FakeBrowser()
    eng.execute([
        {"op": "lease_acquire", "agent_id": "t", "task": "b", "ttl_sec": 30},
        {"op": "browser_wait", "text": "Settings", "timeout": 5},
    ])
    assert seen["timeout"] == 5000.0  # 5 seconds -> 5000 ms


def test_resolve_settings_aria_label():
    from aether.browser import BrowserEngine

    class FakePage:
        async def evaluate(self, js):
            return [
                {"ref": 0, "text": "", "name": "", "aria": "Settings", "title": "", "placeholder": ""},
                {"ref": 1, "text": "Home library", "name": "", "aria": "", "title": "", "placeholder": ""},
            ]

    eng = BrowserEngine.__new__(BrowserEngine)

    async def _run():
        return await eng._resolve_text_ref(FakePage(), "Settings")

    hit = asyncio.run(_run())
    assert hit is not None
    assert hit["ref"] == 0


def test_wait_change_dead_target_fails_fast():
    c = SmartController.__new__(SmartController)
    c._focus_pid = 424242
    c._focus_window_id = 1
    c.backend = type("B", (), {"name": "stub"})()
    c._metrics = {"waits": 0}
    c.similarity_threshold = 0.1
    c._target_alive = lambda pid=None, hwnd=None: {"alive": False, "reason": "pid_dead", "pid": 424242}
    c._uia_call = lambda fn, timeout_s=2.5, default=None: default
    c.observe = lambda *a, **k: (_ for _ in ()).throw(AssertionError("observe should not hang"))
    # bind methods
    c.wait_change = SmartController.wait_change.__get__(c, SmartController)
    c.wait_until = SmartController.wait_until.__get__(c, SmartController)
    c._find_visible_label = lambda needle_l: None
    t0 = time.time()
    out = c.wait_change(timeout=10.0, poll=0.1, expect="NeverAppear")
    elapsed = time.time() - t0
    assert out.success is False
    assert "dead" in (out.message or "").lower()
    assert elapsed < 5.0


def test_wait_gone_dead_window_is_gone():
    c = SmartController.__new__(SmartController)
    c._focus_pid = 1
    c._focus_window_id = 1
    c.backend = type("B", (), {"name": "stub"})()
    c._metrics = {"waits": 0}
    c._target_alive = lambda pid=None, hwnd=None: {"alive": False, "reason": "hwnd_dead"}
    c._find_visible_label = lambda needle_l: (_ for _ in ()).throw(AssertionError("no uia"))
    c.wait_gone = SmartController.wait_gone.__get__(c, SmartController)
    out = c.wait_gone("Settings", timeout=5.0, poll=0.1)
    assert out.success is True
    assert "dead" in (out.message or "").lower()


def test_unknown_app_fails_closed():
    out = resolve_launch_target(app="definitely_not_an_app_zzzx")
    assert out.get("ok") is False


def test_notepad_resolves():
    out = resolve_launch_target(app="notepad")
    assert out.get("ok") is True
