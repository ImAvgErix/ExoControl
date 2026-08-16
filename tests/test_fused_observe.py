"""Fused observe: default OCR on, session hit cache, no silent low-conf click."""
from __future__ import annotations

import inspect

from aether.exec_engine import ExoExecEngine
from aether.smart import ActionOutcome, SmartController
from aether import session as exo_session


def _bare_controller() -> SmartController:
    c = SmartController.__new__(SmartController)
    c._focus_pid = 7
    c._focus_window_id = 11
    c._focus_monitor = None
    c._focus_rect = (0, 0, 200, 100)
    c._metrics = {"clicks": 0, "types": 0, "batches": 0, "memory_hits": 0, "waits": 0, "fills": 0}
    c._timings = {}
    c._safety_prechecked = True
    c.max_retries = 0
    c.verify = False
    c.similarity_threshold = 0.1
    c.backend = type("B", (), {"name": "stub"})()
    c.macros = type("M", (), {"is_recording": lambda self: False, "add": lambda *a, **k: None})()
    c.log = type("L", (), {"record": lambda *a, **k: None})()
    c.safety = type("S", (), {"check": lambda *a, **k: (True, "")})()
    c.memory = type("Mem", (), {
        "record_failure": lambda *a, **k: None,
        "record_success": lambda *a, **k: None,
        "invalidate": lambda *a, **k: None,
    })()
    c._focus_process_name = lambda: "stub"
    c._record_stat = lambda *a, **k: None
    c.ui_hash = lambda force=False: "h"
    c.observe = lambda **kw: {}
    c._verify_change = lambda a, b: False
    c._deliver_click = lambda **kw: type("D", (), {"ok": True, "backend": "stub", "message": "ok"})()
    return c


def test_compact_observe_default_include_ocr_true_and_payload_keys():
    sig = inspect.signature(SmartController.compact_observe)
    assert sig.parameters["include_ocr"].default is True

    c = _bare_controller()
    c.read_ui = lambda **k: {
        "ok": True,
        "pid": 7,
        "title": "Stub",
        "labels": [],
        "values": [],
        "value_entries": [],
        "elements": [],
    }
    c.window_state = lambda hwnd=None: {"known": True, "rect": [0, 0, 200, 100]}
    c.perception = type("P", (), {
        "ocr_available": lambda self: False,
        "capture": lambda self, monitor=1, region=None: None,
        "_run_ocr": lambda self, img: [],
    })()

    out = SmartController.compact_observe(c)
    assert "ocr" in out
    assert "elements" in out
    assert out.get("ocr_available") is False
    assert out.get("ocr_note") == "ocr unavailable"


def test_session_hit_cache_survives_second_execute(tmp_path, monkeypatch):
    monkeypatch.setenv("EXO_LOCK_DIR", str(tmp_path / "locks"))
    monkeypatch.setenv("EXO_STATE_DIR", str(tmp_path / "state"))
    exo_session.clear_hits()

    class Stub:
        def __init__(self):
            self._focus_pid = 7
            self._focus_window_id = 11
            self.last_click = None

        def compact_observe(self, include_ocr=True, **kw):
            return {
                "ok": True,
                "focus_pid": 7,
                "title": "Stub",
                "elements": [
                    {"label": "Save", "kind": "button", "bbox": [10, 10, 40, 30], "source": "opencv"},
                ],
                "ocr": [],
                "a11y": [],
                "hits": [
                    {"label": "Save", "kind": "button", "bbox": [10, 10, 40, 30], "source": "opencv", "visible": True},
                ],
            }

        def smart_click(self, query=None, x=None, y=None, button="left", require_change=False,
                        element_index=None, pid=None, window_id=None, label=None, clicks=1):
            self.last_click = {"query": query, "label": label, "element_index": element_index}
            return ActionOutcome(True, True, f"clicked {label or query}", backend="stub")

        def status(self):
            return {"ok": True}

    ctrl = Stub()
    eng = ExoExecEngine(controller=ctrl)
    first = eng.execute([{"op": "observe"}])
    assert first["ok"] is True
    hits = exo_session.get_hits()
    assert hits, "observe should stash session hits"
    assert hits[0]["ref"] == "e0"
    assert hits[0]["label"] == "Save"

    second = eng.execute(
        [
            {"op": "lease_acquire", "agent_id": "t", "task": "hit", "ttl_sec": 30},
            {"op": "click", "ref": "e0"},
            {"op": "lease_release"},
        ]
    )
    assert second["ok"] is True
    click = next(s for s in second["steps"] if s["op"] == "click")
    assert click["ok"] is True
    assert ctrl.last_click["query"] == "Save" or ctrl.last_click["label"] == "Save"


def test_click_ok_false_when_no_hit_and_no_uia_match():
    exo_session.clear_hits()
    c = _bare_controller()
    c.find_targets = lambda *a, **k: []
    out = SmartController.smart_click(c, query="NoSuchButton")
    assert out.success is False
    guessed = SmartController.smart_click(c, query="NoSuchButton", x=12, y=34)
    assert guessed.success is False
    assert "guessed" in (guessed.message or "").lower() or "no targets" in (guessed.message or "").lower()


def test_fused_hits_capped_at_compact_budget():
    from aether.compact import MAX_COMPACT_REFS

    c = _bare_controller()
    c.read_ui = lambda **k: {
        "ok": True,
        "pid": 7,
        "title": "Stub",
        "labels": [f"L{i}" for i in range(80)],
        "values": [],
        "value_entries": [],
        "elements": [
            {"name": f"E{i}", "role": "button", "bbox": [0, 0, 1, 1], "element_index": i}
            for i in range(80)
        ],
    }
    c.window_state = lambda hwnd=None: {"known": True, "rect": [0, 0, 200, 100]}
    c.perception = type("P", (), {
        "ocr_available": lambda self: False,
        "capture": lambda self, monitor=1, region=None: None,
        "_run_ocr": lambda self, img: [],
    })()
    c._fuse_window_eyes = lambda **k: (
        [{"text": f"t{i}", "bbox": [0, 0, 1, 1]} for i in range(30)],
        [{"label": f"v{i}", "kind": "box", "bbox": [0, 0, 1, 1], "source": "opencv"} for i in range(30)],
        False,
        None,
    )
    out = SmartController.compact_observe(c, max_elements=30, max_ocr=40)
    assert len(out["hits"]) <= MAX_COMPACT_REFS


def test_click_attaches_light_seen_without_jpeg(tmp_path, monkeypatch):
    monkeypatch.setenv("EXO_LOCK_DIR", str(tmp_path / "locks"))
    monkeypatch.setenv("EXO_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("EXO_LIVE_EYES", "0")
    exo_session.clear_hits()

    class Stub:
        def __init__(self):
            self._focus_pid = 7
            self._focus_window_id = 11
            self._eyes = None
            self.last_click = None

        def compact_observe(self, include_ocr=True, **kw):
            return {
                "ok": True,
                "focus_pid": 7,
                "title": "StubApp",
                "elements": [
                    {"label": "Save", "kind": "button", "bbox": [10, 10, 40, 30], "source": "opencv"},
                ],
                "ocr": [],
                "a11y": [],
                "hits": [
                    {"label": "Save", "kind": "button", "bbox": [10, 10, 40, 30], "source": "opencv", "visible": True},
                ],
            }

        def smart_click(self, query=None, x=None, y=None, button="left", require_change=False,
                        element_index=None, pid=None, window_id=None, label=None, clicks=1):
            self.last_click = {"query": query, "label": label}
            return ActionOutcome(True, True, f"clicked {label or query}", backend="stub")

        def hands_glance(self, claimed=None):
            return {
                "ok": True,
                "title": "StubApp",
                "match": str(claimed or "") in {"Save", "e0"},
                "label": claimed,
                "labels": ["Save", "Edit"],
            }

        def status(self):
            return {"ok": True}

    eng = ExoExecEngine(controller=Stub())
    out = eng.execute(
        [
            {"op": "observe"},
            {"op": "lease_acquire", "agent_id": "t", "task": "seen", "ttl_sec": 30},
            {"op": "click", "ref": "e0"},
            {"op": "lease_release"},
        ]
    )
    assert out["ok"] is True
    click = next(s for s in out["steps"] if s["op"] == "click")
    assert click["ok"] is True
    seen = (click.get("result") or {}).get("seen")
    assert isinstance(seen, dict)
    assert seen.get("title") == "StubApp"
    assert seen.get("match") is True
    blob = str(seen).lower()
    assert "screenshot" not in blob
    assert "base64" not in blob
    assert ".jpg" not in blob and "jpeg" not in blob

