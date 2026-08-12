"""Deprecated. The 40-tool aether-driver MCP is gone.

Use:  python -m exo_control.slim_mcp_server
"""
from __future__ import annotations

import sys
import warnings

warnings.warn(
    "exo_control.mcp_server is removed. Start python -m exo_control.slim_mcp_server instead.",
    DeprecationWarning,
    stacklevel=2,
)

from exo_control.slim_mcp_server import (  # noqa: E402
    aether_exec,
    aether_help,
    aether_screenshot,
    exo_exec,
    exo_help,
    exo_screenshot,
    get_engine,
    mcp,
)

__all__ = [
    "mcp",
    "get_engine",
    "exo_exec",
    "exo_screenshot",
    "exo_help",
    "aether_exec",
    "aether_screenshot",
    "aether_help",
]


if __name__ == "__main__":
    print(
        "exo_control.mcp_server is deprecated. Use: python -m exo_control.slim_mcp_server",
        file=sys.stderr,
    )
    mcp.run()
