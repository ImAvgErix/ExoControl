"""MCP entry for Exo Control.

Preferred:
  python -m exo_control.slim_mcp_server

Compat (still supported):
  python -m aether.slim_mcp_server
"""
from __future__ import annotations

from aether.slim_mcp_server import aether_exec, aether_screenshot, engine, mcp

__all__ = ["mcp", "engine", "aether_exec", "aether_screenshot"]

if __name__ == "__main__":
    mcp.run()
