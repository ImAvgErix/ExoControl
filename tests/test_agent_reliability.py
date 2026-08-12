"""Stable refs, finally, last_error, wait compose, fail screenshot envelope."""
from __future__ import annotations

from aether.exec_engine import ExoExecEngine
from aether.smart import ActionOutcome, SmartController


class StubCtrl(SmartController):
    def __init__(self):
        self._focus_pid = 42
        self._focus_window_id = 99
        self._metrics = {"clicks": 0, "types": 0, "batches": 0, "memory_hits": 0, "waits": 0, "fills": 0}
        self._clicks = []
        self.perception = type("P", (), {"capture": lambda *a, **k: None})()

        class _Macros:
            def is_recording(self):
                return False

        self.macros = _Macros()

    def status(self):
        return {"ok": True, "backend": "stub"}

    def read_ui(self, force=True, interactive_only=False, max_elements=120):
        return {
            "ok": True,
            "pid": self._focus_pid,
            "window_id": self._focus_window_id,
            "title": "Stub",
            "labels": ["Save", "Cancel"],
            "values": [],
            "elements": [
                {"element_index": 0, "name": "Save", "role": "button", "bbox": [1, 1, 2, 2]},
                {"element_index": 1, "name": "Cancel", "role": "button", "bbox": [3, 3, 4, 4]},
            ],
            "element_count": 2,
        }

    def compact_observe(self, **kwargs):
        return {
            "ok": True,
            "focus_pid": self._focus_pid,
            "title": "Stub",
            "a11y": [
                {"element_index": 0, "label": "Save", "role": "button"},
                {"element_index": 1, "label": "Cancel", "role": "button"},
            ],
            "a11y_labels": ["Save", "Cancel"],
        }

    def smart_click(self, query=None, x=None, y=None, button="left", require_change=False,
                    element_index=None, pid=None, window_id=None, label=None):
        self._clicks.append(
            {"query": query, "element_index": element_index, "pid": pid, "label": label}
        )
        return ActionOutcome(True, True, f"clicked {label or query or element_index}",
                             backend="stub")

    def smart_type(self, text="", query=None, clear=False, confirm=False):
        return ActionOutcome(True, True, f"typed {text}", backend="stub")

    def window_state(self, hwnd=None):
        return {"known": True, "rect": [0, 0, 100, 100], "title": "Stub"}


def test_read_stamps_refs_and_click_by_ref(tmp_path, monkeypatch):
    monkeypatch.setenv("EXO_LOCK_DIR", str(tmp_path / "locks"))
    monkeypatch.setenv("EXO_STATE_DIR", str(tmp_path / "state"))
    eng = ExoExecEngine(controller=StubCtrl())
    out = eng.execute(
        [
            {"op": "lease_acquire", "agent_id": "t", "task": "ref", "ttl_sec": 30},
            {"op": "read"},
            {"op": "click", "ref": "e0"},
            {"op": "lease_release"},
        ]
    )
    assert out["ok"] is True
    read = out["steps"][1]["result"]
    assert "refs" in read
    assert "e0" in read["refs"]
    assert read["elements"][0]["ref"] == "e0"
    click = out["steps"][2]["result"]
    assert click["ok"] is True
    assert eng.ctrl._clicks[-1]["element_index"] == 0


def test_unknown_ref_fails(tmp_path, monkeypatch):
    monkeypatch.setenv("EXO_LOCK_DIR", str(tmp_path / "locks"))
    monkeypatch.setenv("EXO_STATE_DIR", str(tmp_path / "state"))
    eng = ExoExecEngine(controller=StubCtrl())
    out = eng.execute(
        [
            {"op": "lease_acquire", "agent_id": "t", "task": "ref", "ttl_sec": 30},
            {"op": "click", "ref": "e99"},
        ],
        stop_on_failure=True,
        auto_release_lease=True,
    )
    assert out["ok"] is False
    assert "unknown ref" in (out["steps"][1]["result"].get("error") or "")


def test_finally_runs_on_failure(tmp_path, monkeypatch):
    monkeypatch.setenv("EXO_LOCK_DIR", str(tmp_path / "locks"))
    monkeypatch.setenv("EXO_STATE_DIR", str(tmp_path / "state"))
    eng = ExoExecEngine(controller=StubCtrl())
    out = eng.execute(
        {
            "steps": [
                {"op": "lease_acquire", "agent_id": "t", "task": "f", "ttl_sec": 30},
                {"op": "click", "ref": "missing"},
                {"op": "notify", "title": "nope", "body": "x"},
            ],
            "finally": [
                {"op": "lease_release"},
            ],
        },
        stop_on_failure=True,
        auto_release_lease=False,
        screenshot_on_fail=False,
    )
    phases = [s.get("phase") for s in out["steps"]]
    assert "finally" in phases
    assert any(s["op"] == "lease_release" and s.get("phase") == "finally" for s in out["steps"])
    assert out["finally_ran"] == 1
    assert out["stopped_early"] is True


def test_last_error_after_fail(tmp_path, monkeypatch):
    monkeypatch.setenv("EXO_LOCK_DIR", str(tmp_path / "locks"))
    monkeypatch.setenv("EXO_STATE_DIR", str(tmp_path / "state"))
    eng = ExoExecEngine(controller=StubCtrl())
    eng.execute(
        [
            {"op": "lease_acquire", "agent_id": "t", "task": "e", "ttl_sec": 20},
            {"op": "click", "ref": "nope"},
        ],
        screenshot_on_fail=False,
        auto_release_lease=True,
    )
    le = eng.execute([{"op": "last_error"}])
    body = le["steps"][0]["result"]
    assert body.get("has_error") is True
    assert body.get("op") == "click"


def test_wait_all_seconds(tmp_path, monkeypatch):
    monkeypatch.setenv("EXO_LOCK_DIR", str(tmp_path / "locks"))
    monkeypatch.setenv("EXO_STATE_DIR", str(tmp_path / "state"))
    eng = ExoExecEngine(controller=StubCtrl())
    out = eng.execute(
        [{"op": "wait_all", "all": [{"seconds": 0.01}, {"seconds": 0.01}], "timeout": 2}]
    )
    assert out["ok"] is True
    assert out["steps"][0]["result"]["mode"] == "all"
