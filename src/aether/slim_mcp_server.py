"""Exo Control slim MCP — harness-agnostic eyes/hands for ANY AI.

Any MCP host (Cursor, Claude Desktop, Claude Code, Codex, Windsurf, Continue,
Cline, custom stdio clients) talks to the same tools. Brand aliases:

  exo_exec / aether_exec
  exo_screenshot / aether_screenshot
  exo_help / aether_help

Run:
  python -m exo_control.slim_mcp_server
  python -m aether.slim_mcp_server
"""
from __future__ import annotations

from typing import Any, Dict, Optional, Union

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:  # pragma: no cover
    from mcp.server import MCPServer as FastMCP  # type: ignore

from aether.exec_engine import AetherExecEngine
from aether.ops_catalog import list_ops, mcp_instructions

engine = AetherExecEngine()
mcp = FastMCP("exo-control", instructions=mcp_instructions())


def _run_exec(script: Union[str, list, dict], stop_on_failure: bool = True) -> Dict[str, Any]:
    """Accept JSON string, list of steps, or {\"steps\": [...]} — any host shape."""
    return engine.execute(script, stop_on_failure=stop_on_failure)


@mcp.tool()
def exo_exec(script: Any, stop_on_failure: bool = True) -> Dict[str, Any]:
    """Run a multi-step desktop/browser/OS script (preferred tool name).

    ``script``: JSON array of step objects, a JSON string of that array, or
    ``{\"steps\":[...]}``. First mutating work needs lease_acquire; end with
    lease_release. Call exo_help for the full op catalog.
    """
    return _run_exec(script, stop_on_failure=stop_on_failure)


@mcp.tool()
def aether_exec(script: Any, stop_on_failure: bool = True) -> Dict[str, Any]:
    """Alias of exo_exec — same engine (compat for older prompts/skills)."""
    return _run_exec(script, stop_on_failure=stop_on_failure)


@mcp.tool()
def exo_screenshot(
    title: Optional[str] = None,
    monitor: int = 1,
    max_side: int = 1600,
) -> Dict[str, Any]:
    """Capture window/monitor pixels as JPEG base64 only when structure is insufficient."""
    return engine.screenshot(title=title, monitor=monitor, max_side=max_side)


@mcp.tool()
def aether_screenshot(
    title: Optional[str] = None,
    monitor: int = 1,
    max_side: int = 1600,
) -> Dict[str, Any]:
    """Alias of exo_screenshot."""
    return engine.screenshot(title=title, monitor=monitor, max_side=max_side)


@mcp.tool()
def exo_help(query: Optional[str] = None, detail: bool = False) -> Dict[str, Any]:
    """Op catalog + harness rules for any AI (no lease). Filter with query."""
    return list_ops(query=query, detail=detail)


@mcp.tool()
def aether_help(query: Optional[str] = None, detail: bool = False) -> Dict[str, Any]:
    """Alias of exo_help."""
    return list_ops(query=query, detail=detail)


if __name__ == "__main__":
    mcp.run()
