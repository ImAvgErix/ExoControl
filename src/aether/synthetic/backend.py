"""
SyntheticBackend v1.4 — hardened custom hands.

- Windows: UIA invoke/toggle/select patterns + SendInput + PostMessage
- macOS: AXPress + CGEvent
- Linux: xdotool / XTest
- Parallel per-cursor inject queues (no mid-action interleaving)
- Virtual multi-cursor state
"""
from __future__ import annotations

import sys
from typing import Any, Dict, List, Optional

from ..backends import ActionBackend, DeliveryResult
from .cursor import CursorManager
from .queue import QueueHub


class SyntheticBackend(ActionBackend):
    name = "synthetic"

    def __init__(self):
        self.cursors = CursorManager()
        self.queues = QueueHub()
        self._platform = (
            "win" if sys.platform == "win32"
            else "mac" if sys.platform == "darwin"
            else "linux" if sys.platform.startswith("linux")
            else "unknown"
        )
        self._ok = self._platform in ("win", "mac", "linux")

    def available(self) -> bool:
        return self._ok

    def list_windows(self) -> List[Dict[str, Any]]:
        if self._platform == "win":
            try:
                from ..backends_win import PywinautoBackend
                w = PywinautoBackend()
                if w.available():
                    return w.list_windows()
            except Exception:
                pass
        if self._platform == "mac":
            try:
                from .ax_mac import list_ax_windows
                return list_ax_windows()
            except Exception:
                pass
        if self._platform == "linux":
            import shutil, subprocess
            if shutil.which("wmctrl"):
                r = subprocess.run(["wmctrl", "-lp"], capture_output=True, text=True)
                out = []
                for line in (r.stdout or "").splitlines():
                    parts = line.split(None, 4)
                    if len(parts) >= 5:
                        out.append({
                            "id": parts[0],
                            "pid": int(parts[2]) if parts[2].isdigit() else None,
                            "title": parts[4],
                        })
                return out
        return []

    def get_window_state(self, pid: int, window_id: Optional[int] = None) -> Dict[str, Any]:
        if self._platform == "win":
            try:
                from ..backends_win import PywinautoBackend
                w = PywinautoBackend()
                if w.available():
                    return w.get_window_state(pid, window_id)
            except Exception as e:
                return {"ok": False, "error": str(e), "elements": []}
        return {"ok": False, "elements": [], "error": "a11y tree limited on this platform"}

    def _raw_click(self, x: int, y: int, button: str = "left") -> bool:
        if self._platform == "win":
            from .inject_win import click_abs
            return click_abs(x, y, button)
        if self._platform == "linux":
            from .inject_linux import click_abs
            return click_abs(x, y, button)
        if self._platform == "mac":
            from .inject_mac import click_abs
            return click_abs(x, y, button)
        return False

    def _raw_type(self, text: str) -> bool:
        if self._platform == "win":
            from .inject_win import type_unicode
            return type_unicode(text)
        if self._platform == "linux":
            from .inject_linux import type_text
            return type_text(text)
        if self._platform == "mac":
            from .inject_mac import type_text
            return type_text(text)
        return False

    def _raw_move(self, x: int, y: int) -> bool:
        if self._platform == "win":
            from .inject_win import move_abs
            return move_abs(x, y)
        if self._platform == "linux":
            from .inject_linux import move_abs
            return move_abs(x, y)
        if self._platform == "mac":
            from .inject_mac import move_abs
            return move_abs(x, y)
        return False

    def _do_click(
        self,
        x: Optional[int],
        y: Optional[int],
        button: str,
        pid: Optional[int],
        window_id: Optional[int],
        element_index: Optional[int],
        cursor_id: str,
        title_hint: str = "",
    ) -> DeliveryResult:
        cur = self.cursors.get(cursor_id)
        if pid is not None:
            cur.pid = pid
        if window_id is not None:
            cur.window_id = window_id

        # 1) Windows UIA invoke patterns (best background-friendly)
        if self._platform == "win" and pid is not None and element_index is not None:
            from .uia_invoke import invoke_element
            ok, msg = invoke_element(pid, element_index, window_id)
            if ok:
                return DeliveryResult(True, "synthetic", msg, element_index=element_index)
            # fallback pywinauto click_input
            try:
                from ..backends_win import PywinautoBackend
                w = PywinautoBackend()
                if w.available():
                    return w.click(pid=pid, window_id=window_id, element_index=element_index, button=button)
            except Exception:
                pass

        # 2) macOS AXPress by title hint
        if self._platform == "mac" and pid is not None and title_hint:
            from .ax_mac import ax_press
            ok, msg = ax_press(pid, title_hint=title_hint)
            if ok:
                return DeliveryResult(True, "synthetic", msg)

        # 3) Windows PostMessage background click
        if self._platform == "win" and window_id is not None and x is not None and y is not None:
            try:
                from .inject_win import post_click_hwnd, window_rect
                rect = window_rect(int(window_id))
                if rect:
                    sx, sy = int(x), int(y)
                    cx, cy = (sx - rect[0], sy - rect[1]) if sx >= rect[0] and sy >= rect[1] else (sx, sy)
                    if post_click_hwnd(int(window_id), cx, cy):
                        cur.move(sx, sy)
                        return DeliveryResult(True, "synthetic", f"PostMessage hwnd={window_id}", element_index=element_index)
            except Exception:
                pass

        # 4) Coordinate injection
        if x is None or y is None:
            x, y = cur.pos()
        else:
            cur.move(int(x), int(y))
        ok = self._raw_click(int(x), int(y), button=button)
        return DeliveryResult(
            ok, "synthetic",
            f"inject click ({x},{y}) {self._platform}" if ok else "inject failed",
            element_index=element_index,
        )

    def click(
        self,
        x: Optional[int] = None,
        y: Optional[int] = None,
        button: str = "left",
        pid: Optional[int] = None,
        window_id: Optional[int] = None,
        element_index: Optional[int] = None,
        cursor_id: str = "main",
        title_hint: str = "",
        **kwargs,
    ) -> DeliveryResult:
        q = self.queues.get(cursor_id)
        return q.submit(
            self._do_click, x, y, button, pid, window_id, element_index, cursor_id, title_hint
        )

    def type_text(self, text: str, cursor_id: str = "main", **kwargs) -> DeliveryResult:
        pid = kwargs.get("pid")
        element_index = kwargs.get("element_index")
        window_id = kwargs.get("window_id")

        def _job():
            if self._platform == "win" and pid is not None and element_index is not None:
                from .uia_invoke import set_value
                ok, msg = set_value(int(pid), int(element_index), text, window_id)
                if ok:
                    return DeliveryResult(True, "synthetic", msg)
            ok = self._raw_type(text)
            return DeliveryResult(ok, "synthetic", "typed" if ok else "type failed")

        return self.queues.get(cursor_id).submit(_job)

    def move(self, x: int, y: int, cursor_id: str = "main") -> DeliveryResult:
        def _job():
            cur = self.cursors.get(cursor_id)
            cur.move(x, y)
            ok = self._raw_move(int(x), int(y))
            return DeliveryResult(ok, "synthetic", f"move ({x},{y})")
        return self.queues.get(cursor_id).submit(_job)

    def create_cursor(self, cursor_id: str) -> Dict[str, Any]:
        c = self.cursors.ensure(cursor_id)
        self.queues.get(cursor_id)  # spawn worker
        return {"id": c.id, "x": c.x, "y": c.y}

    def list_cursors(self) -> List[Dict[str, Any]]:
        return self.cursors.list()

    def queue_stats(self) -> Dict[str, Any]:
        return self.queues.stats()
