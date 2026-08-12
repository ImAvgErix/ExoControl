"""Exo Control — preferred public package.

User-facing import: ``import exo_control`` / ``from exo_control import ExoExecEngine``.
Technical compat: ``aether.*`` remains for 1.x (see docs/API-STABILITY.md).
"""
from __future__ import annotations

import sys
from importlib import import_module
from typing import Any, List

import aether as _aether
from aether import __version__ as __version__
from aether import *  # noqa: F403

# Preferred explicit surface for new code
from aether.exec_engine import ExoExecEngine, AetherExecEngine  # noqa: E402
from aether.compact import (  # noqa: E402
    MAX_COMPACT_CHARS,
    MAX_COMPACT_REFS,
    compact_payload,
)
from aether.config import ExoConfig, AetherConfig  # noqa: E402

_SUBMODULES = (
    "exec_engine",
    "browser",
    "compact",
    "files_ops",
    "registry_ops",
    "infra_ops",
    "smart",
    "safety",
    "desktop_lease",
    "clipboard",
    "config",
    "paths",
)


def _alias_submodules() -> None:
    for name in _SUBMODULES:
        mod_name = f"{__name__}.{name}"
        if mod_name in sys.modules:
            continue
        try:
            sys.modules[mod_name] = import_module(f"aether.{name}")
        except ImportError:
            continue


_alias_submodules()

__all__ = sorted(
    {
        "ExoExecEngine",
        "AetherExecEngine",
        "ExoConfig",
        "AetherConfig",
        "MAX_COMPACT_CHARS",
        "MAX_COMPACT_REFS",
        "compact_payload",
        "__version__",
        *[n for n in globals() if not n.startswith("_") and n not in {"sys", "import_module", "Any", "List"}],
    }
)
