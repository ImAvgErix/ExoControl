"""Compat package. Prefer ``from exo_control import ExoExecEngine``.

``import aether`` and ``aether.*`` remain for existing callers.
"""
from __future__ import annotations

from typing import Any

import exo_control
from exo_control import __version__ as __version__


def __getattr__(name: str) -> Any:
    return getattr(exo_control, name)


def __dir__() -> list:
    return sorted(set(getattr(exo_control, "__all__", ())) | set(globals()))


# Submodules live as on-disk shims (aether/exec_engine.py etc.).
# Do not eagerly import every exo_control module — mcp_server warns on import.
