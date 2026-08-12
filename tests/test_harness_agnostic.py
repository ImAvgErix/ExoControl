"""Any AI / any harness surface: help catalog, MCP tool aliases, CLI exec."""
from __future__ import annotations

import json

from aether.ops_catalog import list_ops, mcp_instructions
from aether.exec_engine import AetherExecEngine
from aether.slim_mcp_server import (
    aether_exec,
    aether_help,
    exo_exec,
    exo_help,
    mcp,
)


def test_list_ops_has_surfaces_and_rules():
    out = list_ops(detail=True)
    assert out["ok"] is True
    assert out["count"] >= 40
    assert out["rules"]
    assert "mcp" in out["surfaces"]
    assert "cli" in out["surfaces"]
    assert "python" in out["surfaces"]
    names = {r["op"] for r in out["ops"]}
    assert "help" in names
    assert "launch" in names
    assert "lease_acquire" in names


def test_help_op_via_exec():
    eng = AetherExecEngine()
    r = eng.execute([{"op": "help", "query": "launch", "detail": True}])
    assert r["ok"] is True
    body = r["steps"][0]["result"]
    assert body["ok"] is True
    assert body["count"] >= 1
    assert any(o["op"] == "launch" for o in body["ops"])


def test_capabilities_alias():
    eng = AetherExecEngine()
    r = eng.execute([{"op": "capabilities"}])
    assert r["ok"] is True
    assert r["steps"][0]["result"]["count"] >= 40


def test_mcp_instructions_mention_any_harness():
    text = mcp_instructions().lower()
    assert "any" in text
    assert "lease" in text


def test_mcp_tools_export_exo_and_aether():
    # FastMCP registers functions; ensure our dual names exist as callables
    assert callable(exo_exec)
    assert callable(aether_exec)
    assert callable(exo_help)
    assert callable(aether_help)
    assert mcp is not None


def test_exo_exec_accepts_list_and_string():
    steps = [{"op": "help", "query": "notify"}]
    a = exo_exec(steps)
    assert a["ok"] is True
    b = aether_exec(json.dumps(steps))
    assert b["ok"] is True
    c = exo_exec({"steps": steps})
    assert c["ok"] is True


def test_exo_help_filters():
    out = exo_help(query="monitor")
    assert out["ok"] is True
    # monitors or focus monitor fields
    assert out["count"] >= 1


def test_cli_ops_main(monkeypatch, capsys):
    from aether.cli import main
    code = main(["ops", "lease"])
    assert code == 0
    captured = capsys.readouterr().out
    data = json.loads(captured)
    assert data["ok"] is True
    assert data["count"] >= 1
