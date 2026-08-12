"""
Realtime eyes — continuous screen buffer + change detection + on-demand OCR.

Keeps a fresh frame of the focused window (or primary monitor) so agents can
`read_now()` without paying capture latency every call. OCR runs only when
the frame changes meaningfully (or when forced).
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

try:
    from PIL import Image
    import numpy as np
    HAS_IMG = True
except ImportError:
    HAS_IMG = False


@dataclass
class EyeFrame:
    ts: float
    monitor: int
    region: Optional[Tuple[int, int, int, int]]
    width: int
    height: int
    phash: str
    changed: bool
    labels: List[Dict[str, Any]] = field(default_factory=list)
    a11y_summary: List[Dict[str, Any]] = field(default_factory=list)
    title: str = ""
    pid: Optional[int] = None


class RealtimeEyes:
    def __init__(
        self,
        perception=None,
        fps: float = 6.0,
        ocr_on_change: bool = False,
        focused_window: bool = True,
    ):
        self._perception = perception
        self.fps = max(1.0, float(fps))
        self.ocr_on_change = ocr_on_change
        self.focused_window = focused_window
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._lock = threading.RLock()
        self._frame: Optional[EyeFrame] = None
        self._last_arr = None
        self._last_labels: List[Dict[str, Any]] = []
        self._listeners: List[Callable[[EyeFrame], None]] = []
        self._running = False
        self._prefer_pid: Optional[int] = None
        self._prefer_hwnd: Optional[int] = None
        self._monitor: int = 1

    def attach_perception(self, perception) -> None:
        self._perception = perception

    def set_focus_hint(
        self,
        pid: Optional[int] = None,
        hwnd: Optional[int] = None,
        monitor: Optional[int] = None,
    ) -> None:
        self._prefer_pid = int(pid) if pid is not None else None
        self._prefer_hwnd = int(hwnd) if hwnd is not None else None
        if monitor is not None:
            self._monitor = max(1, int(monitor))

    def set_monitor(self, monitor: int) -> None:
        self._monitor = max(1, int(monitor))

    def start(self) -> Dict[str, Any]:
        if self._running:
            return {"ok": True, "already": True, "fps": self.fps}
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="aether-eyes", daemon=True)
        self._running = True
        self._thread.start()
        return {"ok": True, "fps": self.fps, "focused_window": self.focused_window}

    def stop(self) -> Dict[str, Any]:
        self._stop.set()
        self._running = False
        t = self._thread
        if t and t.is_alive():
            t.join(timeout=2.0)
        return {"ok": True, "stopped": True}

    def on_change(self, cb: Callable[[EyeFrame], None]) -> None:
        self._listeners.append(cb)

    def read_now(self, force_ocr: bool = False) -> Dict[str, Any]:
        """Return latest frame metadata + labels (starts loop if needed)."""
        if not self._running:
            self.start()
        with self._lock:
            need = self._frame is None or force_ocr
        if need:
            self._tick(force_ocr=True)
        with self._lock:
            f = self._frame
            if f is None:
                return {"ok": False, "error": "no frame yet"}
            return {
                "ok": True,
                "ts": f.ts,
                "title": f.title,
                "pid": f.pid,
                "width": f.width,
                "height": f.height,
                "changed": f.changed,
                "phash": f.phash,
                "labels": list(f.labels),
                "a11y": list(f.a11y_summary),
                "age_ms": int((time.time() - f.ts) * 1000),
                "running": self._running,
            }

    def _window_info(self, hwnd: int) -> Tuple[Optional[int], Optional[Tuple[int, int, int, int]], str]:
        try:
            import ctypes
            from ctypes import wintypes
            user32 = ctypes.windll.user32
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(int(hwnd), ctypes.byref(pid))
            rect = wintypes.RECT()
            user32.GetWindowRect(int(hwnd), ctypes.byref(rect))
            length = user32.GetWindowTextLengthW(int(hwnd))
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(int(hwnd), buf, length + 1)
            region = (int(rect.left), int(rect.top), int(rect.right), int(rect.bottom))
            if region[2] <= region[0] or region[3] <= region[1]:
                return int(pid.value), None, buf.value
            return int(pid.value), region, buf.value
        except Exception:
            return None, None, ""

    def _foreground(self) -> Tuple[Optional[int], Optional[Tuple[int, int, int, int]], str]:
        """Return (pid, region ltrb, title) — prefer agent focus hint over OS foreground."""
        try:
            import ctypes
            user32 = ctypes.windll.user32
            if self._prefer_hwnd:
                info = self._window_info(self._prefer_hwnd)
                if info[0] is not None:
                    return info
            if self._prefer_pid is not None:
                # Find largest visible window for preferred pid
                try:
                    from .uia_cache import get_uia_cache
                    for w in get_uia_cache().list_windows():
                        if int(w.get("pid") or -1) == int(self._prefer_pid):
                            return self._window_info(int(w["handle"]))
                except Exception:
                    pass
            hwnd = user32.GetForegroundWindow()
            if not hwnd:
                return None, None, ""
            return self._window_info(int(hwnd))
        except Exception:
            return None, None, ""

    def _phash(self, img) -> str:
        if not HAS_IMG:
            return "0"
        try:
            small = img.convert("L").resize((16, 16))
            arr = np.asarray(small, dtype=np.float32)
            mean = float(arr.mean())
            bits = (arr > mean).astype(np.uint8).flatten()
            # pack to hex
            val = 0
            for b in bits:
                val = (val << 1) | int(b)
            return f"{val:064x}"
        except Exception:
            return str(int(time.time() * 1000))

    def _diff_ratio(self, img) -> float:
        if not HAS_IMG or self._last_arr is None:
            return 1.0
        try:
            small = img.convert("L").resize((64, 36))
            arr = np.asarray(small, dtype=np.float32)
            prev = self._last_arr
            if prev.shape != arr.shape:
                return 1.0
            return float(np.mean(np.abs(arr - prev)) / 255.0)
        except Exception:
            return 1.0

    def _a11y_snapshot(self, pid: Optional[int]) -> List[Dict[str, Any]]:
        if pid is None:
            return []
        try:
            from .uia_cache import get_uia_cache
            tree = get_uia_cache().get_tree(pid)
            out = []
            for e in tree.elements:
                if not e.name or len(e.name) < 2:
                    continue
                # Prefer interactive-ish roles
                role = (e.role or "").lower()
                if role and role not in (
                    "button", "menuitem", "tabitem", "listitem", "hyperlink",
                    "edit", "text", "document", "treeitem", "checkbox", "radiobutton",
                    "combobox", "splitbutton",
                ):
                    # still keep short named controls
                    if len(e.name) > 40:
                        continue
                out.append({
                    "element_index": e.index,
                    "name": e.name[:120],
                    "role": e.role,
                    "bbox": e.bbox,
                })
                if len(out) >= 40:
                    break
            return out
        except Exception:
            return []

    def _tick(self, force_ocr: bool = False) -> None:
        if self._perception is None:
            return
        pid, region, title = (None, None, "")
        if self.focused_window:
            pid, region, title = self._foreground()
        try:
            mon = int(getattr(self, "_monitor", 1) or 1)
            img = self._perception.capture(monitor=mon, region=region)
        except Exception:
            img = None
            mon = int(getattr(self, "_monitor", 1) or 1)
        if img is None:
            # Still publish a11y-only frame so eyes_read is useful without pixels
            a11y = self._a11y_snapshot(pid)
            frame = EyeFrame(
                ts=time.time(), monitor=mon, region=region,
                width=0, height=0, phash="0", changed=True,
                labels=[], a11y_summary=a11y, title=title or "", pid=pid,
            )
            with self._lock:
                self._frame = frame
            return
        ratio = self._diff_ratio(img)
        changed = ratio > 0.012 or force_ocr
        ph = self._phash(img)
        labels = list(self._last_labels)
        if changed and (self.ocr_on_change or force_ocr):
            try:
                # Prefer tesseract path inside PerceptionEngine when available
                labels = self._perception._run_ocr(img) if hasattr(self._perception, "_run_ocr") else []
                if labels is None:
                    labels = []
                # Normalize
                norm = []
                for lab in labels[:60]:
                    if isinstance(lab, dict):
                        norm.append(lab)
                    else:
                        # OCRResult-like
                        try:
                            bbox = lab.bbox.as_list() if hasattr(lab.bbox, "as_list") else list(lab.bbox)
                            norm.append({"text": lab.text, "bbox": bbox, "conf": getattr(lab, "confidence", 0)})
                        except Exception:
                            pass
                labels = norm
                self._last_labels = labels
            except Exception:
                pass
        a11y = self._a11y_snapshot(pid)
        if HAS_IMG:
            try:
                self._last_arr = np.asarray(img.convert("L").resize((64, 36)), dtype=np.float32)
            except Exception:
                pass
        frame = EyeFrame(
            ts=time.time(),
            monitor=mon,
            region=region,
            width=img.size[0],
            height=img.size[1],
            phash=ph,
            changed=changed,
            labels=labels,
            a11y_summary=a11y,
            title=title,
            pid=pid,
        )
        with self._lock:
            self._frame = frame
        if changed:
            for cb in list(self._listeners):
                try:
                    cb(frame)
                except Exception:
                    pass

    def _loop(self) -> None:
        interval = 1.0 / self.fps
        while not self._stop.is_set():
            t0 = time.time()
            try:
                self._tick(force_ocr=False)
            except Exception:
                pass
            elapsed = time.time() - t0
            self._stop.wait(max(0.01, interval - elapsed))


_EYES: Optional[RealtimeEyes] = None
_EYES_LOCK = threading.Lock()


def get_realtime_eyes(perception=None) -> RealtimeEyes:
    global _EYES
    with _EYES_LOCK:
        if _EYES is None:
            _EYES = RealtimeEyes(perception=perception)
        elif perception is not None:
            _EYES.attach_perception(perception)
        return _EYES
