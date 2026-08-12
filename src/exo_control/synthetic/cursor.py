"""Virtual multi-cursor state (does not move the real OS cursor until inject)."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple
import threading
import time


@dataclass
class VirtualCursor:
    id: str
    x: int = 0
    y: int = 0
    buttons_down: set = field(default_factory=set)
    pid: Optional[int] = None
    window_id: Optional[int] = None
    last_move: float = field(default_factory=time.time)

    def move(self, x: int, y: int) -> None:
        self.x, self.y = int(x), int(y)
        self.last_move = time.time()

    def pos(self) -> Tuple[int, int]:
        return self.x, self.y


class CursorManager:
    """Multiple named virtual cursors for parallel agent slots."""

    def __init__(self):
        self._lock = threading.Lock()
        self._cursors: Dict[str, VirtualCursor] = {}
        self._default = "main"
        self.ensure(self._default)

    def ensure(self, cursor_id: str = "main") -> VirtualCursor:
        with self._lock:
            if cursor_id not in self._cursors:
                self._cursors[cursor_id] = VirtualCursor(id=cursor_id)
            return self._cursors[cursor_id]

    def get(self, cursor_id: Optional[str] = None) -> VirtualCursor:
        return self.ensure(cursor_id or self._default)

    def list(self):
        with self._lock:
            return [
                {"id": c.id, "x": c.x, "y": c.y, "pid": c.pid, "window_id": c.window_id}
                for c in self._cursors.values()
            ]
