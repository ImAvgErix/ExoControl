
"""Dedicated STA apartment for Windows UIA / COM-safe work.

QueueHub cursor workers are plain Python threads (often MTA). UIA and
pywinauto hang when Invoke runs off the owning STA. All QueueHub job
bodies (and UIA helpers) hop onto this single STA thread.
"""
from __future__ import annotations

import queue
import sys
import threading
from typing import Any, Callable, Optional

_IS_WIN = sys.platform == "win32"

_job_q: "queue.Queue[Optional[tuple]]" = queue.Queue()
_thread: Optional[threading.Thread] = None
_ready = threading.Event()
_start_lock = threading.Lock()
_tls = threading.local()


def on_sta_thread() -> bool:
    return bool(getattr(_tls, "is_sta", False))


def _sta_main() -> None:
    _tls.is_sta = True
    if _IS_WIN:
        try:
            import ctypes
            # COINIT_APARTMENTTHREADED = 0x2
            ctypes.windll.ole32.CoInitializeEx(None, 0x2)
        except Exception:
            pass
    _ready.set()
    while True:
        item = _job_q.get()
        if item is None:
            break
        fn, args, kwargs, box, ev = item
        try:
            box.append(fn(*args, **kwargs))
        except BaseException as e:  # noqa: BLE001 - must deliver to waiter
            box.append(e)
        finally:
            ev.set()


def _ensure_sta() -> None:
    global _thread
    with _start_lock:
        if _thread is not None and _thread.is_alive():
            return
        _ready.clear()
        _thread = threading.Thread(target=_sta_main, name="aether-sta", daemon=True)
        _thread.start()
    _ready.wait(timeout=5.0)


def call_on_sta(fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    """Run fn on the dedicated STA thread. Inline if already there (or non-Windows)."""
    if not _IS_WIN:
        return fn(*args, **kwargs)
    if on_sta_thread():
        return fn(*args, **kwargs)
    _ensure_sta()
    box: list = []
    ev = threading.Event()
    _job_q.put((fn, args, kwargs, box, ev))
    if not ev.wait(timeout=120.0):
        raise TimeoutError("STA marshal timeout")
    if not box:
        return None
    if isinstance(box[0], BaseException):
        raise box[0]
    return box[0]
