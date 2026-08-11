"""Aether Slim MCP — one script tool and one pixel tool.

Inspired by script-first browser harnesses: agents receive two stable schemas
instead of paying for Aether's full desktop/browser tool catalog every turn.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:
    from mcp.server import MCPServer as FastMCP

from aether.exec_engine import AetherExecEngine


engine = AetherExecEngine()
mcp = FastMCP(
    "aether",
    instructions=(
        "Use aether_exec for UIA-first Windows and browser workflows. Pass a JSON array "
        "of steps such as [{\"op\":\"focus\",\"title\":\"Exo Launcher\"},"
        "{\"op\":\"click\",\"query\":\"Settings\",\"require_change\":true},"
        "{\"op\":\"verify\",\"expect\":[\"Store backends\"]}]. "
        "Prefer read/verify over screenshots. Use aether_screenshot only when pixels matter."
    ),
)


@mcp.tool()
def aether_exec(script: str, stop_on_failure: bool = True) -> Dict[str, Any]:
    """Run a verified multi-step desktop/browser script in one persistent process.

    Supported desktop ops: status, windows, focus, read, observe, click, type,
    scroll, drag, hotkey, keys, fill, wait, wait_gone, wait_change, verify,
    clipboard_get, clipboard_set, stats, screenshot/shot, cdp_discover, wait_cdp,
    launch (env/wait_cdp), open, window_min, window_max, window_restore, window_close.

    Supported browser ops: browser_connect, browser_spaces,
    browser_create_space, browser_navigate, browser_snapshot, browser_click,
    browser_type, browser_press, browser_scroll, browser_wait, browser_fill,
    browser_eval, browser_close_space.
    """
    return engine.execute(script, stop_on_failure=stop_on_failure)


@mcp.tool()
def aether_screenshot(
    title: Optional[str] = None,
    monitor: int = 1,
    max_side: int = 1600,
) -> Dict[str, Any]:
    """Capture focused-window pixels as JPEG base64 only when structure is insufficient."""
    return engine.screenshot(title=title, monitor=monitor, max_side=max_side)


if __name__ == "__main__":
    mcp.run()
