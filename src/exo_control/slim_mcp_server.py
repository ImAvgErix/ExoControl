"""MCP entry for Exo Control — any AI harness.

Preferred:
  python -m exo_control.slim_mcp_server

Compat:
  python -m aether.slim_mcp_server

Tools (exo_* preferred, aether_* aliases):
  exo_exec, exo_screenshot, exo_help
  aether_exec, aether_screenshot, aether_help
"""
from __future__ import annotations

from aether.slim_mcp_server import (
    aether_exec,
    aether_help,
    aether_screenshot,
    engine,
    exo_exec,
    exo_help,
    exo_screenshot,
    mcp,
)

__all__ = [
    "mcp",
    "engine",
    "exo_exec",
    "exo_screenshot",
    "exo_help",
    "aether_exec",
    "aether_screenshot",
    "aether_help",
]

if __name__ == "__main__":
    mcp.run()
