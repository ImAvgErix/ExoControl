"""Exo Control slim MCP — harness-agnostic eyes/hands for ANY AI.

Preferred:
  python -m exo_control.slim_mcp_server

Tools: exo_exec, exo_screenshot, exo_help
Optional aether_* aliases when EXO_MCP_ALIASES=1.
"""
from __future__ import annotations

from typing import Any, Dict, Optional, Union

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:  # pragma: no cover
    from mcp.server import MCPServer as FastMCP  # type: ignore

from exo_control.ops_catalog import list_ops, mcp_instructions
from exo_control.policy import allow_mcp_aliases, identity

_engine = None
mcp = FastMCP("exo-control", instructions=mcp_instructions())


def get_engine():
    global _engine
    if _engine is None:
        from exo_control.exec_engine import ExoExecEngine
        _engine = ExoExecEngine()
    return _engine


def _run_exec(script: Union[str, list, dict], stop_on_failure: bool = True) -> Dict[str, Any]:
    return get_engine().execute(script, stop_on_failure=stop_on_failure)


@mcp.tool()
def exo_exec(script: Any, stop_on_failure: bool = True) -> Dict[str, Any]:
    """Run a multi-step desktop/browser/OS script.

    ``script``: JSON array of step objects, a JSON string of that array, or
    ``{\"steps\":[...],\"finally\":[...]}``. First mutating work needs
    lease_acquire; end with lease_release. Call exo_help for ops.
    """
    return _run_exec(script, stop_on_failure=stop_on_failure)


@mcp.tool()
def exo_screenshot(
    title: Optional[str] = None,
    monitor: int = 1,
    max_side: int = 1600,
) -> Dict[str, Any]:
    """JPEG of a window/monitor. Requires an active desktop lease (same as op screenshot)."""
    return get_engine().screenshot_checked(title=title, monitor=monitor, max_side=max_side)


@mcp.tool()
def exo_help(query: Optional[str] = None, detail: bool = False) -> Dict[str, Any]:
    """Op catalog. Default is the core ops; detail=true or query=… for the rest."""
    out = list_ops(query=query, detail=detail)
    out["identity"] = identity()
    return out


def aether_exec(script: Any, stop_on_failure: bool = True) -> Dict[str, Any]:
    """Compat alias of exo_exec (registered only when EXO_MCP_ALIASES=1)."""
    return _run_exec(script, stop_on_failure=stop_on_failure)


def aether_screenshot(
    title: Optional[str] = None,
    monitor: int = 1,
    max_side: int = 1600,
) -> Dict[str, Any]:
    """Compat alias of exo_screenshot."""
    return get_engine().screenshot_checked(title=title, monitor=monitor, max_side=max_side)


def aether_help(query: Optional[str] = None, detail: bool = False) -> Dict[str, Any]:
    """Compat alias of exo_help."""
    return exo_help(query=query, detail=detail)


if allow_mcp_aliases():
    mcp.tool()(aether_exec)
    mcp.tool()(aether_screenshot)
    mcp.tool()(aether_help)


if __name__ == "__main__":
    mcp.run()
