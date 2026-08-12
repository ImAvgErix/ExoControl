def test_exo_control_slim_mcp_module_importable():
    import exo_control.slim_mcp_server as mod
    assert hasattr(mod, "mcp")
    assert hasattr(mod.mcp, "run")
    assert hasattr(mod, "exo_exec")
    assert hasattr(mod, "aether_exec")
    assert hasattr(mod, "exo_help")


def test_readme_prefers_exo_control_mcp_entry():
    from pathlib import Path
    text = Path("README.md").read_text(encoding="utf-8")
    assert "exo_control.slim_mcp_server" in text
    # preferred args should appear; compat may still be mentioned in prose
    assert '"args": ["-m", "exo_control.slim_mcp_server"]' in text or "exo_control.slim_mcp_server" in text
    assert "any harness" in text.lower() or "any AI" in text or "Any AI" in text
    assert "exo_exec" in text


def test_agents_md_exists_for_any_model():
    from pathlib import Path
    text = Path("AGENTS.md").read_text(encoding="utf-8")
    assert "lease_acquire" in text
    assert "exo_exec" in text
