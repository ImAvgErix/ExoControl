"""Exo Control — realtime PC eyes/hands for any AI (MCP + CLI + Python)."""
from __future__ import annotations

from typing import Any

__version__ = "2.2.0"

# Preferred public names. Heavy modules load on first attribute access.
__all__ = [
    "ExoExecEngine",
    "AetherExecEngine",
    "ExoConfig",
    "AetherConfig",
    "SafetyGate",
    "SafetyConfig",
    "PerceptionEngine",
    "ActionEngine",
    "SmartController",
    "Target",
    "ActionOutcome",
    "CuaBackend",
    "LocalBackend",
    "SyntheticBackend",
    "PywinautoBackend",
    "get_best_backend",
    "LocalGrounder",
    "GroundedElement",
    "UIMemory",
    "list_monitor_dicts",
    "get_monitor",
    "filter_windows_for_monitor",
    "MacroStore",
    "CursorManager",
    "VirtualCursor",
    "QueueHub",
    "BrowserEngine",
    "BrowserEngineSync",
    "MAX_COMPACT_CHARS",
    "MAX_COMPACT_REFS",
    "compact_payload",
    "__version__",
]

_LAZY = {
    "ExoExecEngine": ("exo_control.exec_engine", "ExoExecEngine"),
    "AetherExecEngine": ("exo_control.exec_engine", "AetherExecEngine"),
    "ExoConfig": ("exo_control.config", "ExoConfig"),
    "AetherConfig": ("exo_control.config", "AetherConfig"),
    "SafetyGate": ("exo_control.safety", "SafetyGate"),
    "SafetyConfig": ("exo_control.safety", "SafetyConfig"),
    "PerceptionEngine": ("exo_control.perception", "PerceptionEngine"),
    "ActionEngine": ("exo_control.action", "ActionEngine"),
    "SmartController": ("exo_control.smart", "SmartController"),
    "Target": ("exo_control.smart", "Target"),
    "ActionOutcome": ("exo_control.smart", "ActionOutcome"),
    "CuaBackend": ("exo_control.backends", "CuaBackend"),
    "LocalBackend": ("exo_control.backends", "LocalBackend"),
    "get_best_backend": ("exo_control.backends", "get_best_backend"),
    "LocalGrounder": ("exo_control.grounding", "LocalGrounder"),
    "GroundedElement": ("exo_control.grounding", "GroundedElement"),
    "UIMemory": ("exo_control.memory", "UIMemory"),
    "list_monitor_dicts": ("exo_control.monitors", "list_monitor_dicts"),
    "get_monitor": ("exo_control.monitors", "get_monitor"),
    "filter_windows_for_monitor": ("exo_control.monitors", "filter_windows_for_monitor"),
    "MacroStore": ("exo_control.macros", "MacroStore"),
    "MAX_COMPACT_CHARS": ("exo_control.compact", "MAX_COMPACT_CHARS"),
    "MAX_COMPACT_REFS": ("exo_control.compact", "MAX_COMPACT_REFS"),
    "compact_payload": ("exo_control.compact", "compact_payload"),
}


def __getattr__(name: str) -> Any:
    if name in {"SyntheticBackend", "CursorManager", "VirtualCursor", "QueueHub"}:
        try:
            from exo_control import synthetic as syn
            return getattr(syn, name)
        except Exception as exc:
            raise AttributeError(name) from exc
    if name == "PywinautoBackend":
        try:
            from exo_control.backends_win import PywinautoBackend
            return PywinautoBackend
        except Exception as exc:
            raise AttributeError(name) from exc
    if name in {"BrowserEngine", "BrowserEngineSync"}:
        try:
            from exo_control.browser import BrowserEngine, BrowserEngineSync
            return BrowserEngine if name == "BrowserEngine" else BrowserEngineSync
        except Exception as exc:
            raise AttributeError(name) from exc
    spec = _LAZY.get(name)
    if spec is None:
        raise AttributeError(f"module 'exo_control' has no attribute {name!r}")
    mod_name, attr = spec
    from importlib import import_module
    return getattr(import_module(mod_name), attr)


def __dir__() -> list:
    return sorted(set(__all__) | set(globals()))
