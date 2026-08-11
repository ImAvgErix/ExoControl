# Exo Control

> **Exo Control — realtime PC eyes and hands for any AI agent. Compact. Leased. Honest.**

**Announce-GA cleared 2026-08-11** for v0.1. Capability bar: [Jarvis OS](docs/JARVIS-OS.md) (stamped). Prefer import `exo_control`; `aether.*` remains stable per [API-STABILITY.md](docs/API-STABILITY.md). P1 trails are not claimed.

Realtime desktop (UIA) + browser (DOM/CDP) + files + registry + OS infrastructure for **any** AI harness — Cursor, Claude Desktop, Codex, custom agents, scripts. Compact refs by default, batched exec, screenshots only on ask or structure miss.

| Doc | Role |
|-----|------|
| [docs/JARVIS-OS.md](docs/JARVIS-OS.md) | Capability bar (Floor + P0) |
| [docs/CHARTER.md](docs/CHARTER.md) | Product charter |
| [SECURITY.md](SECURITY.md) | Hard stops, lease, confirm gates |

Repo: [ImAvgErix/ExoControl](https://github.com/ImAvgErix/ExoControl). Related app: [ExoLauncher](https://github.com/ImAvgErix/ExoLauncher) (separate).

## Requirements

- Windows (primary today)
- Python 3.10+

## Install

```bash
git clone https://github.com/ImAvgErix/ExoControl.git
cd ExoControl
pip install -e .
playwright install chromium
```

Preferred import: `exo_control` (re-exports). `aether.*` stays stable for v0.1 — see [docs/API-STABILITY.md](docs/API-STABILITY.md). CLI: `exo-control` (and compat `aether`).

## Cursor (MCP)

Add to your Cursor MCP config (`mcp.json` or Cursor Settings → MCP):

```json
{
  "mcpServers": {
    "exo-control": {
      "command": "python",
      "args": ["-m", "exo_control.slim_mcp_server"]
    }
  }
}
```

Use a venv/`python` that has this package installed. MCP module: `exo_control.slim_mcp_server` (compat: `aether.slim_mcp_server`). Prefer one batched `aether_exec` script over chatty single clicks.

## Claude Desktop (MCP)

Same server in Claude Desktop config (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "exo-control": {
      "command": "python",
      "args": ["-m", "exo_control.slim_mcp_server"]
    }
  }
}
```

Restart Claude Desktop after editing. Point `command` at the interpreter that has the package installed if `python` is ambiguous.

## CLI

```bash
exo-control --help
aether --help
aether windows
aether lease status
aether script steps.json
```

Equivalent: `python -m aether.cli …`.

## Python

```python
from exo_control.exec_engine import AetherExecEngine

eng = AetherExecEngine()
eng.execute([
    {"op": "lease_acquire", "agent_id": "my-agent", "task": "demo", "ttl_sec": 120},
    {"op": "launch", "name": "notepad"},
    {"op": "wait_window", "title_contains": "Notepad", "timeout": 10},
    {"op": "type", "text": "hello from exo-control"},
    {"op": "lease_release"},
])
```

## Safety

- Desktop lease: one agent holds the hands at a time
- Destructive / kill / registry write / service mutate require `confirm=true`
- Hard denies: anti-cheat tampering, credential dumping, silent elevation
- Details: [SECURITY.md](SECURITY.md)

## Status

**Announce-GA cleared 2026-08-11** for v0.1. Jarvis OS stamped. Package `exo-control` with dual `exo_control` / `aether.*` imports. P1 trails optional and unclaimed.

## License

MIT
