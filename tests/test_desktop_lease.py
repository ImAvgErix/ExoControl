"""Desktop lease + wait_cdp coverage (temp lock/state dirs)."""
from __future__ import annotations

import time
from unittest.mock import patch

import pytest

from aether import desktop_lease
from aether.exec_engine import AetherExecEngine


@pytest.fixture()
def lease_dirs(tmp_path, monkeypatch):
    lock = tmp_path / "locks"
    state = tmp_path / "state"
    lock.mkdir()
    state.mkdir()
    monkeypatch.setenv("AETHER_LOCK_DIR", str(lock))
    monkeypatch.setenv("AETHER_STATE_DIR", str(state))
    monkeypatch.setenv("AETHER_NOTIFY_STUB", "1")
    # Ensure no leftover claim
    desktop_lease.release("noop")
    yield tmp_path


def test_acquire_conflict_release(lease_dirs):
    a = desktop_lease.acquire("agent-a", "task-a", ttl_sec=60)
    assert a["ok"] is True
    assert a.get("token")
    b = desktop_lease.acquire("agent-b", "task-b", ttl_sec=60)
    assert b["ok"] is False
    assert b["holder"] == "agent-a"
    assert b["task"] == "task-a"
    st = desktop_lease.status()
    assert st["held"] is True
    assert st["holder"] == "agent-a"
    rel = desktop_lease.release(a["token"])
    assert rel["ok"] is True and rel["released"] is True
    st2 = desktop_lease.status()
    assert st2["held"] is False
    c = desktop_lease.acquire("agent-c", "task-c", ttl_sec=60)
    assert c["ok"] is True
    desktop_lease.release(c["token"])


def test_expire_allows_steal(lease_dirs):
    a = desktop_lease.acquire("agent-a", "short", ttl_sec=0.1)
    assert a["ok"] is True
    time.sleep(0.15)
    # status should report not held (expired)
    st = desktop_lease.status()
    assert st["held"] is False
    b = desktop_lease.acquire("agent-b", "steal", ttl_sec=30)
    assert b["ok"] is True
    desktop_lease.release(b["token"])


def test_renew_extends(lease_dirs):
    a = desktop_lease.acquire("agent-a", "renew-me", ttl_sec=2)
    assert a["ok"] is True
    r = desktop_lease.renew(a["token"], ttl_sec=60)
    assert r["ok"] is True
    # foreign token cannot renew
    bad = desktop_lease.renew("not-a-real-token", ttl_sec=60)
    assert bad["ok"] is False
    desktop_lease.release(a["token"])


def test_exec_mutating_requires_lease(lease_dirs):
    class Stub:
        def __init__(self):
            self._focus_window_id = 10
            self._focus_pid = 1

        def status(self):
            return {"ok": True}

        def smart_hotkey(self, keys):
            class R:
                success = True
                message = "ok"
                verified = True
                backend = "stub"
                attempts = 1
                from_memory = False
                target = None

            return R()

        def compact_observe(self, include_ocr=True):
            return {"ok": True, "elements": []}

    eng = AetherExecEngine(controller=Stub())
    denied = eng.execute([{"op": "keys", "keys": "ctrl+l"}])
    assert denied["ok"] is False
    assert denied["steps"][0]["result"]["error"] == "desktop lease required"

    ok = eng.execute(
        [
            {"op": "lease_acquire", "agent": "t", "task": "keys", "ttl_sec": 30},
            {"op": "keys", "keys": "ctrl+l"},
            {"op": "lease_release"},
        ]
    )
    assert ok["ok"] is True
    assert ok["steps"][1]["result"]["success"] is True


def test_wait_cdp_stub(lease_dirs, monkeypatch):
    calls = {"n": 0}

    def fake_discover(extra_ports=None):
        calls["n"] += 1
        if calls["n"] < 3:
            return []
        return [{"endpoint": "http://127.0.0.1:9229", "port": 9229, "browser": "stub", "targets": []}]

    monkeypatch.setattr("aether.exo_bridge.discover_cdp_endpoints", fake_discover)

    class Stub:
        def status(self):
            return {"ok": True}

    eng = AetherExecEngine(controller=Stub())
    result = eng.execute([{"op": "wait_cdp", "timeout": 5, "poll": 0.01}])
    assert result["ok"] is True
    assert result["steps"][0]["result"]["count"] == 1
    assert calls["n"] >= 3

    # timeout path
    monkeypatch.setattr("aether.exo_bridge.discover_cdp_endpoints", lambda extra_ports=None: [])
    miss = eng.execute([{"op": "wait_cdp", "timeout": 0.05, "poll": 0.01}])
    assert miss["ok"] is False
    assert miss["steps"][0]["result"]["ok"] is False


def test_notify_stub_and_files_list(lease_dirs, tmp_path):
    class Stub:
        def status(self):
            return {"ok": True}

    eng = AetherExecEngine(controller=Stub())
    # notify is mutating — need lease
    out = eng.execute(
        [
            {"op": "lease_acquire", "agent": "t", "task": "notify", "ttl_sec": 30},
            {"op": "notify", "title": "Hi", "body": "there", "stub": True},
            {"op": "lease_release"},
        ]
    )
    assert out["ok"] is True
    assert out["steps"][1]["result"]["stub"] is True

    d = tmp_path / "files"
    d.mkdir()
    (d / "a.txt").write_text("x", encoding="utf-8")
    listed = eng.execute([{"op": "files_list", "path": str(d)}])
    assert listed["ok"] is True
    names = [e["name"] for e in listed["steps"][0]["result"]["entries"]]
    assert "a.txt" in names
