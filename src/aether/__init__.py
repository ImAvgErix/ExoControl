"""Exo Control v1.0.0 — Jarvis OS complete (compact eyes, multi-monitor, persistent UI memory, fuzzy launch)."""
__version__ = "1.0.0"
from .perception import PerceptionEngine
from .action import ActionEngine
from .smart import SmartController, Target, ActionOutcome
from .backends import CuaBackend, LocalBackend, get_best_backend
from .grounding import LocalGrounder, GroundedElement
from .memory import UIMemory
from .monitors import list_monitor_dicts, get_monitor, filter_windows_for_monitor
from .safety import SafetyGate, SafetyConfig
from .config import AetherConfig
from .macros import MacroStore
try:
    from .synthetic import SyntheticBackend, CursorManager, VirtualCursor, QueueHub
except ImportError:
    SyntheticBackend = CursorManager = VirtualCursor = QueueHub = None
try:
    from .backends_win import PywinautoBackend
except ImportError:
    PywinautoBackend = None
try:
    from .browser import BrowserEngine, BrowserEngineSync
except ImportError:
    BrowserEngine = BrowserEngineSync = None
__all__ = [
    "PerceptionEngine", "ActionEngine", "SmartController", "Target", "ActionOutcome",
    "CuaBackend", "LocalBackend", "SyntheticBackend", "PywinautoBackend", "get_best_backend",
    "LocalGrounder", "GroundedElement", "UIMemory", "SafetyGate", "SafetyConfig",
    "list_monitor_dicts", "get_monitor", "filter_windows_for_monitor",
    "AetherConfig", "MacroStore", "CursorManager", "VirtualCursor", "QueueHub",
    "BrowserEngine", "BrowserEngineSync", "__version__",
]
