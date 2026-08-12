"""Regression tests for type/verify honesty, proc name kill, exec envelope."""
from __future__ import annotations

from aether import infra_ops
from aether.exec_engine import AetherExecEngine, _step_ok
from aether.uia_cache import CachedElement


def test_step_ok_normalizes_missing_ok_field():
    assert _step_ok({"version": "1.0.2", "backend": "synthetic"}) is True
    assert _step_ok({"ok": True}) is True
    assert _step_ok({"ok": False}) is False
    assert _step_ok({"success": False}) is False
    assert _step_ok({"error": "x"}) is False


def test_cached_element_exposes_value_in_as_dict():
    el = CachedElement(index=0, name="", role="document", bbox=[0, 0, 10, 10], value="hello world")
    d = el.as_dict()
    assert d["value"] == "hello world"
    assert el.text == "hello world"


def test_proc_kill_protected_by_name_without_pid():
    out = infra_ops.kill_proc(name="EasyAntiCheat", confirm=True)
    assert out["ok"] is False
    assert out.get("reason") == "protected_process" or out.get("error") == "protected_process"


def test_proc_kill_name_requires_confirm():
    out = infra_ops.kill_proc(name="notepad", confirm=False)
    assert out["ok"] is False
    assert "confirm" in out["error"]


def test_proc_kill_via_exec_name_protected(tmp_path, monkeypatch):
    monkeypatch.setenv("AETHER_LOCK_DIR", str(tmp_path / "locks"))
    monkeypatch.setenv("AETHER_STATE_DIR", str(tmp_path / "state"))
    eng = AetherExecEngine()
    out = eng.execute(
        [
            {"op": "lease_acquire", "agent_id": "t", "task": "k", "ttl_sec": 20},
            {"op": "proc_kill", "name": "battleye", "confirm": True},
        ],
        stop_on_failure=False,
        auto_release_lease=True,
    )
    # step envelope always has ok
    assert all("ok" in s for s in out["steps"])
    kill_step = next(s for s in out["steps"] if s["op"] == "proc_kill")
    assert kill_step["ok"] is False
    assert kill_step["result"].get("reason") == "protected_process" or kill_step["result"].get("error") == "protected_process"


def test_auto_release_lease_on_failure(tmp_path, monkeypatch):
    monkeypatch.setenv("AETHER_LOCK_DIR", str(tmp_path / "locks"))
    monkeypatch.setenv("AETHER_STATE_DIR", str(tmp_path / "state"))
    from aether import desktop_lease

    eng = AetherExecEngine()
    out = eng.execute(
        [
            {"op": "lease_acquire", "agent_id": "auto-rel", "task": "fail", "ttl_sec": 30},
            {"op": "proc_kill", "name": "easyanticheat", "confirm": True},
            {"op": "notify", "title": "should not run", "body": "x"},
        ],
        stop_on_failure=True,
        auto_release_lease=True,
    )
    assert out.get("auto_released_lease") is True
    assert out["stopped_early"] is True
    st = desktop_lease.status()
    assert st.get("held") is False
    # auto lease_release appended
    assert any(s.get("op") == "lease_release" and s.get("auto") for s in out["steps"])


def test_status_has_ok_and_honest_ax_mac():
    eng = AetherExecEngine()
    out = eng.execute([{"op": "status"}])
    assert out["ok"] is True
    body = out["steps"][0]["result"]
    assert body.get("ok") is True
    assert out["steps"][0]["ok"] is True
    import sys
    assert body["capabilities"]["ax_mac"] is (sys.platform == "darwin")
