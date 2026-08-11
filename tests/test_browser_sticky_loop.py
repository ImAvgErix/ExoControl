
"""BrowserEngineSync sticky loop + lazy start for CDP attach."""
from __future__ import annotations

import asyncio

import pytest

from aether.browser import BrowserEngineSync
from aether.exec_engine import AetherExecEngine


@pytest.fixture
def lease_home(tmp_path, monkeypatch):
    monkeypatch.setenv("AETHER_LOCK_DIR", str(tmp_path / "locks"))
    monkeypatch.setenv("AETHER_STATE_DIR", str(tmp_path / "state"))
    yield tmp_path


def test_sticky_loop_reused_across_ops():
    sync = BrowserEngineSync(headless=True)
    try:
        async def one():
            return asyncio.get_running_loop()

        async def two():
            return asyncio.get_running_loop()

        loop1 = sync._run(one())
        loop2 = sync._run(two())
        assert loop1 is loop2
        assert sync.loop_id == id(loop1)
    finally:
        sync.stop()


def test_get_browser_does_not_start(monkeypatch, lease_home):
    started = {"n": 0}

    class FakeSync:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def start(self):
            started["n"] += 1
            return {"ok": True}

        def connect_cdp(self, endpoint="http://127.0.0.1:9222"):
            return {"ok": True, "endpoint": endpoint, "started_calls": started["n"]}

    monkeypatch.setattr("aether.browser.BrowserEngineSync", FakeSync)
    eng = AetherExecEngine(controller=type("C", (), {"list_windows": lambda self: []})())
    b = eng._get_browser()
    assert started["n"] == 0
    out = b.connect_cdp("http://127.0.0.1:9229")
    assert out["ok"] is True
    assert started["n"] == 0


def test_home_library_synonym_match():
    from aether.browser import BrowserEngine

    class FakePage:
        async def evaluate(self, js):
            return [
                {"ref": 0, "text": "", "name": "", "aria": "Library", "title": "", "placeholder": ""},
                {"ref": 1, "text": "", "name": "", "aria": "Settings", "title": "", "placeholder": ""},
            ]

    eng = BrowserEngine.__new__(BrowserEngine)

    async def _run():
        return await eng._resolve_text_ref(FakePage(), "Home library")

    hit = asyncio.run(_run())
    assert hit is not None
    assert hit["ref"] == 0


def test_browser_fill_text_value_sugar(monkeypatch, lease_home):
    seen = {}

    class FakeBrowser:
        def fill_form(self, fields, space_id=None):
            seen["fields"] = fields
            return {"ok": True, "results": [{"field": k, "ok": True} for k in fields]}

    eng = AetherExecEngine(controller=type("C", (), {"list_windows": lambda self: []})())
    eng._browser = FakeBrowser()
    result = eng.execute([
        {"op": "lease_acquire", "agent_id": "f", "task": "fill", "ttl_sec": 30},
        {"op": "browser_fill", "text": "Search to install", "value": "celeste"},
    ])
    assert result["ok"] is True, result
    assert seen["fields"] == {"Search to install": "celeste"}

