
"""Dual-cursor queues: parallel workers, no mid-action interleave."""
from __future__ import annotations

import threading
import time
from typing import Any, Dict, List

from aether.synthetic.queue import QueueHub


def test_queuehub_mid_action_no_interleave():
    hub = QueueHub()
    timeline: List[str] = []
    lock = threading.Lock()

    def make_job(name: str, hold: float = 0.05):
        def _job():
            with lock:
                timeline.append(f"{name}:start")
            time.sleep(hold)
            with lock:
                timeline.append(f"{name}:end")
            return name
        return _job

    q1 = hub.get("worker-1")
    q2 = hub.get("worker-2")

    # Fire both nearly together; mid-action lock must keep start/end pairs nested, not interleaved.
    results = [None, None]
    errors = [None, None]

    def run(idx, q, name):
        try:
            results[idx] = q.submit(make_job(name, 0.08), timeout=5.0)
        except Exception as e:
            errors[idx] = e

    t1 = threading.Thread(target=run, args=(0, q1, "w1"))
    t2 = threading.Thread(target=run, args=(1, q2, "w2"))
    t1.start(); t2.start()
    t1.join(5); t2.join(5)
    assert errors == [None, None], errors
    assert set(results) == {"w1", "w2"}
    # No interleave: after a start, next event must be that same name's end before another start.
    assert len(timeline) == 4
    i = 0
    while i < len(timeline):
        start = timeline[i]
        assert start.endswith(":start"), timeline
        name = start.split(":")[0]
        assert timeline[i + 1] == f"{name}:end", timeline
        i += 2


def test_smartcontroller_cursor_exec_api():
    from aether.synthetic.backend import SyntheticBackend
    from aether.smart import SmartController

    # Prefer synthetic backend so queues exist
    ctrl = SmartController(prefer_cua=False, verify=False)
    # Force synthetic-like queues if backend lacks them
    if not hasattr(ctrl.backend, "queues"):
        from aether.synthetic.queue import QueueHub
        ctrl.backend.queues = QueueHub()
        ctrl.backend.create_cursor = lambda cursor_id: {"id": cursor_id, "x": 0, "y": 0}
        ctrl.backend.list_cursors = lambda: [{"id": "worker-1"}, {"id": "worker-2"}]

    c1 = ctrl.create_cursor("worker-1")
    c2 = ctrl.create_cursor("worker-2")
    assert c1.get("ok") is not False
    assert c2.get("ok") is not False
    assert hasattr(ctrl, "cursor_exec")

    # cursor handle exposes smart_click
    h = ctrl.cursor("worker-1")
    assert h.cursor_id == "worker-1"
    assert callable(h.smart_click)

    # Non-interleave via cursor queues with stub jobs on hub
    hub = ctrl.backend.queues
    timeline: List[str] = []

    def job(tag):
        def _j():
            timeline.append(f"{tag}:start")
            time.sleep(0.05)
            timeline.append(f"{tag}:end")
            return tag
        return _j

    out = {}
    def run(cid, tag):
        out[tag] = hub.get(cid).submit(job(tag), timeout=5)

    threads = [
        threading.Thread(target=run, args=("worker-1", "a")),
        threading.Thread(target=run, args=("worker-2", "b")),
    ]
    for t in threads: t.start()
    for t in threads: t.join(5)
    assert set(out) == {"a", "b"}
    i = 0
    while i < len(timeline):
        name = timeline[i].split(":")[0]
        assert timeline[i + 1] == f"{name}:end", timeline
        i += 2
