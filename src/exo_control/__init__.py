"""Exo Control public package (v0.1 rename window).

``aether.*`` remains the stable import path for existing harnesses.
``exo_control`` is the preferred new name and re-exports the same surface,
including common submodules (``exo_control.exec_engine``, etc.).
"""
from __future__ import annotations

import sys
from importlib import import_module
from typing import Any, List

import aether as _aether
from aether import __version__ as __version__
from aether import *  # noqa: F403

# Preferred explicit surface for new code
from aether.exec_engine import AetherExecEngine  # noqa: E402
from aether.compact import (  # noqa: E402
    MAX_COMPACT_CHARS,
    MAX_COMPACT_REFS,
    compact_payload,
)

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
        "AetherExecEngine",
        "MAX_COMPACT_CHARS",
        "MAX_COMPACT_REFS",
        "compact_payload",
        "__version__",
        *[n for n in globals() if not n.startswith("_") and n not in {"sys", "import_module", "Any", "List"}],
    }
)
