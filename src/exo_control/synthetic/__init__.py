"""Custom synthetic input stack — virtual cursors, OS inject, UIA/AX, parallel queues."""
from .cursor import VirtualCursor, CursorManager
from .backend import SyntheticBackend
from .queue import QueueHub, CursorQueue
__all__ = ["VirtualCursor", "CursorManager", "SyntheticBackend", "QueueHub", "CursorQueue"]
