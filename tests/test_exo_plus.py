
"""Exo Control Plus: notify real path, clipboard image set, browser text click, wait_window."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

import pytest

from aether.exec_engine import AetherExecEngine, _notify_toast, _wait_window
from aether.clipboard import set_clipboard_image


@pytest.fixture
def lease_home(tmp_path, monkeypatch):
    monkeypatch.setenv("AETHER_LOCK_DIR", str(tmp_path / "locks"))
    monkeypatch.setenv("AETHER_STATE_DIR", str(tmp_path / "state"))
    yield tmp_path



class _WinStub:
    def __init__(self, windows=None):
        self._windows = windows or []

    def list_windows(self):
        return list(self._windows)


def test_notify_real_path_invokes_powershell(monkeypatch, lease_home):
    """Without stub env, notify must call PowerShell toast helper (not stub result)."""
    monkeypatch.delenv("AETHER_NOTIFY_STUB", raising=False)
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        class R:
            returncode = 0
            stdout = "notifyicon\n"
            stderr = ""
        return R()

    monkeypatch.setattr("subprocess.run", fake_run)
    out = _notify_toast("Aether", "hello")
    assert out["ok"] is True
    assert out.get("method") in {"burnttoast", "winrt", "notifyicon"}
    assert calls, "expected powershell invocation"
    assert any("powershell" in str(c[0]).lower() or (isinstance(c, list) and "powershell" in c[0].lower()) for c in calls)

    eng = AetherExecEngine(controller=_WinStub())
    result = eng.execute([{"op": "notify", "title": "Aether", "body": "hello"}])
    assert result["ok"] is True
    step = result["steps"][0]["result"]
    assert step.get("stub") is not True
    assert step.get("ok") is True


def test_clipboard_image_set_roundtrip(tmp_path, lease_home, monkeypatch):
    from PIL import Image

    img_path = tmp_path / "put.png"
    Image.new("RGB", (6, 4), color=(1, 2, 3)).save(img_path)

    set_calls = []

    def fake_set(path):
        set_calls.append(path)
        return {"ok": True, "path": str(path), "method": "stub", "size": [6, 4]}

    monkeypatch.setattr("aether.clipboard.set_clipboard_image", fake_set)

    eng = AetherExecEngine(controller=_WinStub())
    result = eng.execute([
        {"op": "lease_acquire", "agent_id": "t", "task": "clip", "ttl_sec": 30},
        {"op": "clipboard_image_set", "path": str(img_path)},
    ])
    assert result["ok"] is True, result
    img_step = [s for s in result["steps"] if s["op"] == "clipboard_image_set"][0]
    assert img_step["result"].get("ok") is True
    assert set_calls


def test_clipboard_image_set_missing_file():
    out = set_clipboard_image(str(Path("C:/no/such/clip-image-zzz.png")))
    assert out["ok"] is False
    assert "not found" in out["error"]


def test_browser_click_resolves_text(monkeypatch, lease_home):
    class FakeBrowser:
        def click(self, ref=None, selector=None, x=None, y=None, space_id=None,
                  text=None, name=None, query=None):
            return {
                "ok": True,
                "method": "text",
                "ref": 3,
                "query": text or name or query,
                "matched_text": "Settings",
            }

        def wait_for(self, text=None, selector=None, timeout=15000, space_id=None,
                     name=None, query=None):
            return {"ok": True, "method": "text", "text": text or name or query, "ref": 3}

    eng = AetherExecEngine(controller=_WinStub())
    eng._browser = FakeBrowser()
    # browser ops need lease
    result = eng.execute([
        {"op": "lease_acquire", "agent_id": "b", "task": "browser", "ttl_sec": 30},
        {"op": "browser_click", "text": "Settings"},
        {"op": "browser_wait", "name": "Home library", "timeout": 1000},
    ])
    assert result["ok"] is True, result
    click = result["steps"][1]["result"]
    assert click["ok"] is True
    assert click["method"] == "text"
    assert click["query"] == "Settings"
    wait = result["steps"][2]["result"]
    assert wait["ok"] is True
    assert "Home library" in (wait.get("text") or "")


def test_resolve_text_ref_scoring():
    import asyncio
    from aether.browser import BrowserEngine

    class FakePage:
        async def evaluate(self, js):
            return [
                {"ref": 0, "text": "Home", "name": "", "aria": ""},
                {"ref": 1, "text": "Settings", "name": "", "aria": ""},
                {"ref": 2, "text": "Home library", "name": "", "aria": ""},
            ]

    eng = BrowserEngine.__new__(BrowserEngine)
    page = FakePage()

    async def _run():
        hit = await eng._resolve_text_ref(page, "Settings")
        hit2 = await eng._resolve_text_ref(page, "library")
        return hit, hit2

    hit, hit2 = asyncio.run(_run())
    assert hit["ref"] == 1
    assert hit2["ref"] == 2


def test_wait_window_title_and_timeout(lease_home):
    wins = [{"title": "Exo Launcher", "pid": 4242, "handle": 99}]
    ctrl = _WinStub(wins)
    out = _wait_window(ctrl, {"title": "Exo", "timeout": 1.0, "poll": 0.05})
    assert out["ok"] is True
    assert out["pid"] == 4242

    miss = _wait_window(ctrl, {"title": "NopeMissing", "timeout": 0.2, "poll": 0.05})
    assert miss["ok"] is False
    assert miss["error"] == "window not found"

    eng = AetherExecEngine(controller=ctrl)
    result = eng.execute([{"op": "wait_window", "title": "Launcher", "timeout": 1.0}])
    assert result["ok"] is True
    assert result["steps"][0]["result"]["pid"] == 4242
