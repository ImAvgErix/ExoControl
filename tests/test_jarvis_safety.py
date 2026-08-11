"""JARVIS 1.7 safety: verify fail-closed, kill switch, rate limits, destructive gate,
browser_snapshot stub, action_log, cross-engine lease release.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock

import pytest

from aether import desktop_lease
from aether.exec_engine import AetherExecEngine
from aether.safety import SafetyGate, SafetyConfig
from aether.smart import ActionOutcome, SmartController


@pytest.fixture
def lease_home(tmp_path, monkeypatch):
    monkeypatch.setenv("AETHER_DESKTOP_LOCK", str(tmp_path / "desktop.lock"))
    monkeypatch.setenv("AETHER_LOCK_DIR", str(tmp_path / "locks"))
    monkeypatch.setenv("AETHER_STATE_DIR", str(tmp_path / "state"))
    yield tmp_path


class SafetyStub:
    """Minimal controller with SafetyGate + injectable actions (no real PC)."""

    def __init__(self, max_actions: int = 90, max_clicks: int = 45):
        self.safety = SafetyGate(SafetyConfig(
            max_actions_per_minute=max_actions,
            max_clicks_per_minute=max_clicks,
            min_action_interval_s=0.0,
        ))
        self._safety_prechecked = False
        self.injects = 0
        self.log_records: List[Dict[str, Any]] = []
        # Default focused window so act-without-focus only trips when cleared.
        self._focus_window_id = 10
        self._focus_pid = 1

        class _Log:
            def __init__(self, outer):
                self.outer = outer

            def record(self, event, **payload):
                self.outer.log_records.append({"event": event, **payload, "ts": time.time()})

            def tail(self, n=20):
                return list(self.outer.log_records[-n:])

        self.log = _Log(self)

    def recent_actions(self, n=20):
        return self.log.tail(n)

    def status(self):
        return {"ok": True}

    def smart_focus(self, title=None, pid=None):
        self._focus_window_id = 10
        self._focus_pid = pid or 1
        return {
            "ok": True,
            "pid": self._focus_pid,
            "window_id": self._focus_window_id,
            "title": title or "Focused",
            "raised": True,
        }

    def window_state(self, window_id):
        return {
            "known": True,
            "rect": [0, 0, 20, 10],
            "visible": True,
            "title": "Focused",
            "window_id": window_id,
        }

    @property
    def perception(self):
        class _P:
            def capture(self, monitor=1, region=None):
                from PIL import Image
                return Image.new("RGB", (20, 10), color=(1, 2, 3))
        return _P()

    def kill_switch(self, armed: bool = True):
        if armed:
            self.safety.arm_kill_switch()
        else:
            self.safety.disarm_kill_switch()
        return {"kill_switch": self.safety.config.kill_switch}

    def smart_hotkey(self, keys):
        self.injects += 1
        return ActionOutcome(True, True, f"hotkey {keys}", backend="stub")

    def smart_click(self, query=None, x=None, y=None, button="left", require_change=False):
        self.injects += 1
        return ActionOutcome(True, True, f"click {query}", backend="stub")

    def smart_type(self, text="", query=None, clear=False, confirm=False):
        self.injects += 1
        return ActionOutcome(True, True, f"type {text}", backend="stub")

    def verify_ui(self, expect=None, expect_gone=None, timeout=6.0, poll=0.25):
        # Fail-closed stub: never finds anything
        if isinstance(expect, str):
            expect = [expect]
        expect = [e for e in (expect or []) if str(e).strip()]
        if not expect and not expect_gone:
            return {"ok": False, "error": "verify requires expect or expect_gone", "missing": []}
        return {
            "ok": False,
            "found": {},
            "missing": list(expect),
            "still_present": [],
            "elapsed": 0.0,
        }

    def wait_change(self, timeout=10.0, poll=0.35, threshold=None, expect=None):
        needle = None
        if isinstance(expect, (list, tuple)):
            parts = [str(x).strip() for x in expect if str(x).strip()]
            needle = parts[0] if parts else None
        elif expect is not None:
            needle = str(expect).strip() or None
        if needle:
            return ActionOutcome(False, False, f"wait_change expected text absent: {needle}", backend="stub")
        return ActionOutcome(False, False, "No change detected", backend="stub")


def test_verify_fail_closed_absent_text(lease_home):
    eng = AetherExecEngine(controller=SafetyStub())
    out = eng.execute([{"op": "verify", "expect": ["DefinitelyMissingLabelXYZ"], "timeout": 0.05}])
    assert out["ok"] is False
    res = out["steps"][0]["result"]
    assert res["ok"] is False
    assert "DefinitelyMissingLabelXYZ" in (res.get("missing") or [])


def test_wait_change_expect_fail_closed(lease_home):
    eng = AetherExecEngine(controller=SafetyStub())
    out = eng.execute([{"op": "wait_change", "expect": "NopeNotOnScreen", "timeout": 0.05}])
    assert out["ok"] is False
    res = out["steps"][0]["result"]
    assert res.get("ok") is False or res.get("success") is False
    assert "absent" in (res.get("message") or "").lower() or res.get("success") is False


def test_kill_switch_blocks_mutating_zero_injects(lease_home):
    stub = SafetyStub()
    eng = AetherExecEngine(controller=stub)
    armed = eng.execute([{"op": "kill_switch", "armed": True}])
    assert armed["ok"] is True
    assert armed["steps"][0]["result"]["armed"] is True

    blocked = eng.execute(
        [
            {"op": "lease_acquire", "agent": "k", "task": "ks", "ttl_sec": 30},
            {"op": "keys", "keys": "ctrl+l"},
        ]
    )
    assert blocked["ok"] is False
    err = blocked["steps"][1]["result"].get("error") or ""
    assert "kill_switch" in err
    assert stub.injects == 0

    eng.execute([{"op": "kill_switch", "armed": False}])
    # Prior script acquired a lease then stopped on kill_switch — clear sticky claim.
    eng.execute([{"op": "lease_force_release"}])
    ok = eng.execute(
        [
            {"op": "lease_acquire", "agent": "k2", "task": "ks2", "ttl_sec": 30},
            {"op": "keys", "keys": "ctrl+l"},
            {"op": "lease_release"},
        ]
    )
    assert ok["ok"] is True, ok
    assert stub.injects == 1


def test_rate_limit_blocks_with_reason(lease_home, monkeypatch):
    stub = SafetyStub(max_actions=2, max_clicks=2)
    eng = AetherExecEngine(controller=stub)
    # bypass min interval
    stub.safety.config.min_action_interval_s = 0.0
    script = [
        {"op": "lease_acquire", "agent": "r", "task": "rate", "ttl_sec": 30},
        {"op": "keys", "keys": "a"},
        {"op": "keys", "keys": "b"},
        {"op": "keys", "keys": "c"},
    ]
    out = eng.execute(script, stop_on_failure=False)
    # third keys should be rate-blocked
    errs = [s["result"].get("error", "") for s in out["steps"] if s["op"] == "keys"]
    assert any("rate limit" in e for e in errs)
    assert stub.injects <= 2


def test_destructive_requires_confirm(lease_home):
    stub = SafetyStub()
    eng = AetherExecEngine(controller=stub)
    denied = eng.execute(
        [
            {"op": "lease_acquire", "agent": "d", "task": "dest", "ttl_sec": 30},
            {"op": "type", "text": "please delete all backups"},
        ]
    )
    assert denied["ok"] is False
    err = denied["steps"][1]["result"].get("error") or ""
    assert "confirm" in err.lower() or "destructive" in err.lower()
    assert stub.injects == 0

    # cleanup lease
    st = desktop_lease.status()
    if st.get("token"):
        desktop_lease.release(st["token"])

    ok = eng.execute(
        [
            {"op": "lease_acquire", "agent": "d2", "task": "dest2", "ttl_sec": 30},
            {"op": "type", "text": "please delete all backups", "confirm": True},
            {"op": "lease_release"},
        ]
    )
    assert ok["ok"] is True
    assert stub.injects == 1


def test_browser_snapshot_stubbed(lease_home, monkeypatch):
    stub = SafetyStub()
    eng = AetherExecEngine(controller=stub)

    class FakeBrowser:
        def start(self):
            return None

        def snapshot(self, space_id=None, include_screenshot=False):
            return {
                "ok": True,
                "space_id": space_id or "s1",
                "url": "https://example.test/",
                "title": "Example",
                "text": "hello snapshot",
                "elements": [{"ref": 0, "tag": "a", "text": "Home"}],
            }

    eng._browser = FakeBrowser()
    out = eng.execute(
        [
            {"op": "lease_acquire", "agent": "b", "task": "snap", "ttl_sec": 30},
            {"op": "browser_snapshot"},
            {"op": "lease_release"},
        ]
    )
    assert out["ok"] is True
    snap = out["steps"][1]["result"]
    assert snap["title"] == "Example"
    assert "hello snapshot" in snap["text"]
    assert isinstance(snap.get("elements"), list)


def test_action_log_records_mutating(lease_home):
    stub = SafetyStub()
    eng = AetherExecEngine(controller=stub)
    out = eng.execute(
        [
            {"op": "lease_acquire", "agent": "l", "task": "log", "ttl_sec": 30},
            {"op": "keys", "keys": "ctrl+a"},
            {"op": "action_log", "n": 5},
            {"op": "lease_release"},
        ]
    )
    assert out["ok"] is True
    log = out["steps"][2]["result"]
    assert log["ok"] is True
    assert log["count"] >= 1
    ops = [e.get("op") or e.get("event") for e in log["entries"]]
    assert any(o == "keys" for o in ops)


def test_cross_engine_release_by_token(lease_home):
    eng_a = AetherExecEngine(controller=SafetyStub())
    acq = eng_a.execute([{"op": "lease_acquire", "agent": "alpha", "task": "hold", "ttl_sec": 60}])
    assert acq["ok"] is True
    token = acq["steps"][0]["result"]["token"]

    # Fresh engine (no in-process token) releases by explicit token from status
    eng_b = AetherExecEngine(controller=SafetyStub())
    st = eng_b.execute([{"op": "lease_status"}])["steps"][0]["result"]
    assert st["held"] is True
    assert st["token"] == token

    rel = eng_b.execute([{"op": "lease_release", "token": token}])
    assert rel["ok"] is True
    assert rel["steps"][0]["result"].get("released") is True

    eng_c = AetherExecEngine(controller=SafetyStub())
    again = eng_c.execute([{"op": "lease_acquire", "agent": "gamma", "task": "after", "ttl_sec": 30}])
    assert again["ok"] is True
    desktop_lease.release(again["steps"][0]["result"]["token"])


def test_lease_force_release_and_acquire(lease_home):
    a = desktop_lease.acquire("sticky", "stuck", ttl_sec=120)
    assert a["ok"] is True
    eng = AetherExecEngine(controller=SafetyStub())
    forced = eng.execute([{"op": "lease_force_release"}])
    assert forced["ok"] is True
    assert forced["steps"][0]["result"].get("released") is True
    b = eng.execute([{"op": "lease_acquire", "agent": "fresh", "task": "ok", "ttl_sec": 30}])
    assert b["ok"] is True
    desktop_lease.release(b["steps"][0]["result"]["token"])


def test_safety_gate_unit_destructive_and_kill():
    g = SafetyGate(SafetyConfig(min_action_interval_s=0.0, max_actions_per_minute=10))
    ok, why = g.check("action", text="rm -rf /tmp/x", confirm=False)
    assert ok is False and "confirm" in why
    ok2, _ = g.check("action", text="rm -rf /tmp/x", confirm=True)
    assert ok2 is True
    g.arm_kill_switch()
    ok3, why3 = g.check("click", text="ok")
    assert ok3 is False and "kill_switch" in why3


def test_act_without_focus_hard_fail(lease_home):
    stub = SafetyStub()
    stub._focus_window_id = None
    stub._focus_pid = None
    eng = AetherExecEngine(controller=stub)
    # acquire lease then click with no focus
    r = eng.execute([
        {"op": "lease_acquire", "agent_id": "coder", "task": "nofocus", "ttl_sec": 60},
        {"op": "click", "x": 1, "y": 1},
    ])
    assert r["ok"] is False
    err = str(r["steps"][-1]["result"].get("error", "")).lower()
    assert "act-without-focus" in err or "no focused" in err


def test_screenshot_wrong_window_fail(tmp_path, lease_home):
    stub = SafetyStub()
    def bad_focus(title=None, pid=None):
        stub._focus_window_id = 10
        stub._focus_pid = 1
        return {"ok": True, "pid": 1, "window_id": 10, "title": "Other App", "raised": True}
    stub.smart_focus = bad_focus  # type: ignore
    stub.window_state = lambda window_id: {
        "known": True, "rect": [0, 0, 20, 10], "visible": True,
        "title": "Other App", "window_id": window_id,
    }
    eng = AetherExecEngine(controller=stub)
    out = str(tmp_path / "w.png")
    r = eng.execute([
        {"op": "lease_acquire", "agent_id": "coder", "task": "shot", "ttl_sec": 60},
        {"op": "shot", "path": out, "title": "Exo Launcher"},
    ])
    assert r["ok"] is False
    err = str(r["steps"][-1]["result"].get("error", "")).lower()
    assert "wrong-window" in err or "mismatch" in err


def test_cross_execute_acquire_then_release(lease_home):
    stub = SafetyStub()
    eng = AetherExecEngine(controller=stub)
    acq = eng.execute([{"op": "lease_acquire", "agent_id": "g", "task": "cross", "ttl_sec": 60}])
    assert acq["ok"] is True
    assert acq["steps"][0]["result"].get("ok") is True
    assert desktop_lease.status().get("held") is True
    rel = eng.execute([{"op": "lease_release"}])
    assert rel["ok"] is True, rel
    assert rel["steps"][0]["result"].get("ok") is True
    st = desktop_lease.status()
    assert st.get("held") is False, st
