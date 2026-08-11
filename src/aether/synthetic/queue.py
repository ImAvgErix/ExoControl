
"""
Per-cursor inject queues - parallel agent slots without interleaving mid-action.
Each cursor has its own worker thread and serial queue.

Jobs execute on the dedicated STA thread (Windows) so UIA/COM injects do not
hang. Nested submit from inside a running job runs inline (no self-deadlock).
"""
from __future__ import annotations
import queue
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

from .sta_marshal import call_on_sta

# Cross-thread: set while a QueueHub job body is executing (on STA).
_executing = threading.local()


def _in_cursor_job() -> bool:
    return bool(getattr(_executing, "active", False))


@dataclass
class Job:
    fn: Callable
    args: tuple
    kwargs: dict
    result_box: list
    event: threading.Event


class CursorQueue:
    def __init__(self, cursor_id: str, mid_action_lock: Optional[threading.Lock] = None):
        self.cursor_id = cursor_id
        self._mid_action_lock = mid_action_lock or threading.Lock()
        self._q: queue.Queue = queue.Queue()
        self._thread = threading.Thread(target=self._run, name=f"aether-cursor-{cursor_id}", daemon=True)
        self._alive = True
        self._thread.start()
        self.processed = 0

    def _run_job(self, job: Job) -> Any:
        def _body():
            _executing.active = True
            _executing.cursor_id = self.cursor_id
            try:
                return job.fn(*job.args, **job.kwargs)
            finally:
                _executing.active = False
                _executing.cursor_id = None

        return call_on_sta(_body)

    def _run(self) -> None:
        while self._alive:
            try:
                job: Job = self._q.get(timeout=0.2)
            except queue.Empty:
                continue
            try:
                # Serialize mid-action across ALL cursors - parallel queues, no interleave.
                with self._mid_action_lock:
                    result = self._run_job(job)
                job.result_box.append(result)
            except Exception as e:
                job.result_box.append(e)
            finally:
                job.event.set()
                self.processed += 1
                self._q.task_done()

    def submit(self, fn: Callable, *args, timeout: float = 30.0, **kwargs) -> Any:
        # Nested submit from inside a cursor job (cursor_exec -> click): run inline
        # on the current (STA) thread. mid_action_lock is already held by outer job.
        if _in_cursor_job():
            return fn(*args, **kwargs)

        box: list = []
        ev = threading.Event()
        self._q.put(Job(fn=fn, args=args, kwargs=kwargs, result_box=box, event=ev))
        if not ev.wait(timeout):
            raise TimeoutError(f"cursor queue {self.cursor_id} timeout")
        if not box:
            return None
        if isinstance(box[0], Exception):
            raise box[0]
        return box[0]

    def stop(self) -> None:
        self._alive = False


class QueueHub:
    def __init__(self):
        self._lock = threading.Lock()
        self._mid_action_lock = threading.Lock()
        self._queues: Dict[str, CursorQueue] = {}

    def get(self, cursor_id: str = "main") -> CursorQueue:
        with self._lock:
            if cursor_id not in self._queues:
                self._queues[cursor_id] = CursorQueue(cursor_id, mid_action_lock=self._mid_action_lock)
            return self._queues[cursor_id]

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                cid: {"processed": q.processed, "pending": q._q.qsize()}
                for cid, q in self._queues.items()
            }
