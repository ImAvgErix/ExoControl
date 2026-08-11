# Exo Control

Harness-agnostic realtime PC control for AI agents: desktop (UIA), browser (DOM/CDP), files, registry, and OS infrastructure.

Works with any MCP host (Cursor, Claude Desktop, …), the CLI, or the Python SDK. Compact refs by default, batched exec, screenshots only on ask or structure miss.

**Pitch:** realtime PC eyes and hands for any AI agent. Compact. Leased. Honest.

**Capability bar:** [docs/JARVIS-OS.md](docs/JARVIS-OS.md) (Jarvis OS). Product clears when Floor + all P0 are [x].

Related app: [ExoLauncher](https://github.com/ImAvgErix/ExoLauncher) (separate repo).

## Requirements

- Windows (primary today)
- Python 3.10+

## Install

`ash
git clone https://github.com/ImAvgErix/ExoControl.git
cd ExoControl
pip install -e .
playwright install chromium
`

Import path is still ether.* during the rename. Installed CLI entry point: ether (and xo-control once the scripts entry is wired).

## Cursor (MCP)

Add to your Cursor MCP config (mcp.json or Cursor Settings → MCP):

`json
{
  \"mcpServers\": {
    \"exo-control\": {
      \"command\": \"python\",
      \"args\": [\"-m\", \"aether.slim_mcp_server\"]
    }
  }
}
`

Use a venv/python that has this package installed. Prefer one batched ether_exec script over chatty single clicks.

## Claude Desktop (MCP)

Same server; put it in Claude Desktop’s config (claude_desktop_config.json):

`json
{
  \"mcpServers\": {
    \"exo-control\": {
      \"command\": \"python\",
      \"args\": [\"-m\", \"aether.slim_mcp_server\"]
    }
  }
}
`

Restart Claude Desktop after editing. Point command at the interpreter that has the package installed if python is ambiguous.

## CLI

`ash
aether --help
aether windows
aether lease status
aether script steps.json
`

Equivalent: python -m aether.cli ….

## Python

`python
from aether.exec_engine import AetherExecEngine

eng = AetherExecEngine()
eng.execute([
    {\"op\": \"lease_acquire\", \"agent_id\": \"my-agent\", \"task\": \"demo\", \"ttl_sec\": 120},
    {\"op\": \"launch\", \"name\": \"notepad\"},
    {\"op\": \"wait_window\", \"title_contains\": \"Notepad\", \"timeout\": 10},
    {\"op\": \"type\", \"text\": \"hello from exo-control\"},
    {\"op\": \"lease_release\"},
])
`

## Safety

- Desktop lease: one agent holds the hands at a time
- Destructive / kill / registry write / service mutate require confirm=true
- Hard denies: anti-cheat tampering, credential dumping, silent elevation
- See [SECURITY.md](SECURITY.md)

## Status

Bootstrap from former local aether-driver (v1.8 lineage). Package name xo-control; modules/CLI still ether until rename completes. **Alpha** until Jarvis OS is stamped.

## License

MIT
