"""Exo Control public package (v0.1 rename window).

Stable import path for v0.1 remains ``aether.*`` — existing MCP/CLI/Python
harnesses keep working. This package re-exports the same surface so new code
can ``import exo_control`` while we complete the rename.
"""
from __future__ import annotations

from aether import *  # noqa: F403
from aether import __version__ as __version__

__all__ = [name for name in globals() if not name.startswith("_")]
