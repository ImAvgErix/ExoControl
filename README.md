# Exo Control

Realtime PC control for **any AI harness** — Cursor, Claude, Codex, custom agents, scripts.

Desktop (UIA) + browser (DOM/CDP) + files + registry + OS infrastructure.
Elite token efficiency: compact refs by default, batched exec, no screenshot spam.

Capability bar: see docs/JARVIS-OS.md (Jarvis OS).
Related app: https://github.com/ImAvgErix/ExoLauncher (separate repo).

## Install

pip install -e .
playwright install chromium

Windows today (primary). Python 3.10+.

## MCP (any MCP host)

{
  "mcpServers": {
    "exo-control": {
      "command": "python",
      "args": ["-m", "aether.slim_mcp_server"]
    }
  }
}

Prefer batched script ops over chatty single clicks.

## CLI

exo-control --help
aether --help

## Python

from aether.exec_engine import AetherExecEngine
eng = AetherExecEngine()
eng.execute([
    {"op": "lease_acquire", "agent_id": "my-agent", "task": "demo", "ttl_sec": 120},
    {"op": "launch", "name": "notepad"},
    {"op": "wait_window", "title_contains": "Notepad", "timeout": 10},
    {"op": "type", "text": "hello from exo-control"},
    {"op": "lease_release"},
])

## Safety

- Desktop lease (one agent holds hands)
- Destructive / kill / registry write / service mutate need confirm=true
- No anti-cheat tampering, credential dumping, or silent elevation

## Status

Bootstrap from former local aether-driver (v1.8 lineage). Import path still aether.* during rename; CLI: exo-control and aether.

## License

MIT
