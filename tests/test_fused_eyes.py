"""Fused-eyes contract: default observe, session hits, honest click."""
from __future__ import annotations

import inspect

from aether.exec_engine import ExoExecEngine
from aether.grounding import fuse_observe_hits
from aether.session import clear_hits, get_hits, lookup_hit, replace_hits
from aether.smart import ActionOutcome, SmartController, Target


def test_compact_observe_default_includes_vision():
    sig = inspect.signature(SmartController.compact_observe)
    assert sig.parameters["include_ocr"].default is True


def test_fuse_observe_hits_assigns_refs_and_sources():
    hits = fuse_observe_hits(
        [{"label": "Send", "role": "button", "bbox": [10, 10, 40, 30], "element_index": 2}],
        [{"label": "icon", "kind": "icon", "bbox": [50, 10, 70, 30], "source": "opencv", "confidence": 0.4}],
        [{"text": "Hello", "bbox": [10, 40, 80, 55], "confidence": 0.8}],
        max_hits=40,
        pid=7,
        window_id=9,
    )
    assert hits
    assert all(h.get("ref", "").startswith("e") for h in hits)
    sources = {h["source"] for h in hits}
    assert sources <= {"uia", "ocr", "opencv", "fused"}
    assert any(h["source"] == "opencv" and h["kind"] == "icon" for h in hits)
    assert any(h.get("label") == "Send" for h in hits)


class EyesCtrl(SmartController):
    def __init__(self):
        self._focus_pid = 42
        self._focus_window_id = 99
        self._metrics = {"clicks": 0, "types": 0, "batches": 0, "memory_hits": 0, "waits": 0, "fills": 0}
        self._clicks = []
        self.perception = type("P", (), {
            "capture": lambda *a, **k: None,
            "ocr_status": lambda *a, **k: "unavailable",
        })()

        class _Macros:
            def is_recording(self):
                return False

        self.macros = _Macros()

    def status(self):
        return {"ok": True, "backend": "stub"}

    def compact_observe(self, include_ocr=True, **kwargs):
        return {
            "ok": True,
            "focus_pid": self._focus_pid,
            "title": "Composer",
            "hits": [
                {"ref": "e0", "label": "icon", "kind": "icon", "role": "icon",
                 "bbox": [100, 200, 124, 224], "source": "opencv", "visible": True},
                {"ref": "e1", "label": "Send", "kind": "button", "role": "button",
                 "bbox": [130, 200, 180, 224], "source": "uia", "visible": True,
                 "element_index": 3},
            ],
            "elements": [{"label": "icon", "kind": "icon", "source": "opencv", "bbox": [100, 200, 124, 224]}],
            "a11y": [{"label": "Send", "role": "button", "element_index": 3}],
            "ocr": "unavailable",
            "ocr_count": 0,
            "element_count": 1,
            "a11y_count": 1,
            "ocr_backend": "unavailable",
        }

    def smart_click(self, query=None, x=None, y=None, button="left", require_change=False,
                    element_index=None, pid=None, window_id=None, label=None, clicks=1,
                    bbox=None, source=None, kind=None):
        self._clicks.append({
            "query": query, "x": x, "y": y, "element_index": element_index,
            "bbox": bbox, "source": source, "kind": kind, "label": label,
        })
        if query == "missing-control" and x is None:
            return ActionOutcome(False, False, "No targets for 'missing-control'", backend="stub")
        return ActionOutcome(True, True, f"clicked {label or query}", backend="stub")

    def glance(self, force_ocr=False):
        return {"ok": True, "title": "Composer", "labels": ["Send"], "via": "a11y"}


def test_session_hit_cache_survives_second_exec(tmp_path, monkeypatch):
    monkeypatch.setenv("EXO_LOCK_DIR", str(tmp_path / "locks"))
    monkeypatch.setenv("EXO_STATE_DIR", str(tmp_path / "state"))
    clear_hits()
    eng = ExoExecEngine(controller=EyesCtrl())
    first = eng.execute(
        [
            {"op": "lease_acquire", "agent_id": "eyes", "task": "fuse", "ttl_sec": 30},
            {"op": "observe"},
        ],
        auto_release_lease=False,
    )
    assert first["ok"] is True
    obs = first["steps"][1]["result"]
    assert obs.get("hits") or obs.get("elements") or obs.get("a11y")
    assert get_hits(), "observe must stash session hits"
    second = eng.execute(
        [
            {"op": "click", "ref": "e0"},
            {"op": "lease_release"},
        ],
        auto_release_lease=False,
    )
    assert second["ok"] is True
    click = second["steps"][0]["result"]
    assert click["ok"] is True
    last = eng.ctrl._clicks[-1]
    assert last.get("bbox") == [100, 200, 124, 224] or last.get("source") == "opencv"


def test_click_prefers_fused_hit_over_coord(tmp_path, monkeypatch):
    monkeypatch.setenv("EXO_LOCK_DIR", str(tmp_path / "locks"))
    monkeypatch.setenv("EXO_STATE_DIR", str(tmp_path / "state"))
    clear_hits()
    replace_hits([{
        "ref": "e0", "label": "icon", "kind": "icon",
        "bbox": [100, 200, 124, 224], "source": "opencv", "visible": True,
    }])
    eng = ExoExecEngine(controller=EyesCtrl())
    out = eng.execute(
        [
            {"op": "lease_acquire", "agent_id": "eyes", "task": "fuse", "ttl_sec": 30},
            {"op": "click", "query": "icon", "x": 12, "y": 34},
            {"op": "lease_release"},
        ]
    )
    assert out["ok"] is True
    last = eng.ctrl._clicks[-1]
    assert last.get("source") == "opencv" or last.get("bbox") == [100, 200, 124, 224]
    assert last.get("x") != 12


def test_click_reports_false_when_target_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("EXO_LOCK_DIR", str(tmp_path / "locks"))
    monkeypatch.setenv("EXO_STATE_DIR", str(tmp_path / "state"))
    clear_hits()
    eng = ExoExecEngine(controller=EyesCtrl())
    out = eng.execute(
        [
            {"op": "lease_acquire", "agent_id": "eyes", "task": "fuse", "ttl_sec": 30},
            {"op": "click", "query": "missing-control"},
        ],
        stop_on_failure=True,
        auto_release_lease=True,
    )
    assert out["ok"] is False
    body = out["steps"][1]["result"]
    assert body.get("ok") is False


def test_lookup_hit_by_kind():
    clear_hits()
    replace_hits([
        {"ref": "e0", "label": "icon", "kind": "icon", "bbox": [1, 2, 3, 4], "source": "opencv", "visible": True},
    ])
    hit = lookup_hit(kind="icon")
    assert hit is not None
    assert hit["ref"] == "e0"
    clear_hits()
    assert lookup_hit(kind="icon") is None
