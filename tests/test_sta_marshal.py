
"""STA marshal + nested QueueHub submit must not hang."""
from __future__ import annotations

import threading
import time

from aether.synthetic.queue import QueueHub
from aether.synthetic.sta_marshal import call_on_sta, on_sta_thread


def test_call_on_sta_runs_on_dedicated_thread():
    names = []

    def _job():
        names.append(threading.current_thread().name)
        return on_sta_thread()

    assert call_on_sta(_job) is True
    assert names == ["aether-sta"]


def test_nested_submit_inside_cursor_job_no_deadlock():
    hub = QueueHub()
    q = hub.get("worker-1")
    seen = []

    def inner():
        seen.append("inner")
        return 42

    def outer():
        # Simulate synthetic backend.click submitting while already in a job
        # (cursor_exec -> execute -> click -> queues.submit).
        return q.submit(inner, timeout=5.0)

    out = q.submit(outer, timeout=5.0)
    assert out == 42
    assert seen == ["inner"]


def test_nested_submit_still_serialized_across_cursors():
    hub = QueueHub()
    timeline = []

    def make(tag, hold=0.05):
        def _j():
            timeline.append(f"{tag}:start")
            time.sleep(hold)
            timeline.append(f"{tag}:end")
            return tag
        return _j

    def outer(tag):
        q = hub.get(tag)
        # nested submit must stay under mid_action
        return q.submit(make(tag), timeout=5.0)

    results = {}
    def run(tag):
        results[tag] = hub.get(tag).submit(lambda: outer(tag), timeout=5.0)

    threads = [threading.Thread(target=run, args=(t,)) for t in ("worker-1", "worker-2")]
    for t in threads:
        t.start()
    for t in threads:
        t.join(5)
    assert set(results) == {"worker-1", "worker-2"}
    i = 0
    while i < len(timeline):
        name = timeline[i].split(":")[0]
        assert timeline[i + 1] == f"{name}:end", timeline
        i += 2
