<p align="center">
  <strong>Exo Control</strong>
</p>

<h1 align="center">Realtime PC eyes and hands for any AI agent</h1>

<p align="center">
  Compact. Leased. Honest. Jarvis OS complete.
</p>

<p align="center">
  <a href="https://github.com/ImAvgErix/ExoControl/releases/latest"><img alt="Latest release" src="https://img.shields.io/github/v/release/ImAvgErix/ExoControl?style=flat-square&label=release&color=79f2c0" /></a>
  <a href="LICENSE"><img alt="MIT license" src="https://img.shields.io/github/license/ImAvgErix/ExoControl?style=flat-square&color=111111" /></a>
  <a href="https://github.com/ImAvgErix/ExoControl/actions"><img alt="Python" src="https://img.shields.io/badge/python-3.10%2B-111111?style=flat-square" /></a>
  <a href="docs/JARVIS-OS.md"><img alt="Jarvis OS" src="https://img.shields.io/badge/Jarvis%20OS-complete-79f2c0?style=flat-square" /></a>
</p>

<p align="center">
  <a href="#install"><strong>Install</strong></a>
  ·
  <a href="#cursor-mcp">Cursor MCP</a>
  ·
  <a href="docs/JARVIS-OS.md">Capability bar</a>
  ·
  <a href="SECURITY.md">Safety</a>
  ·
  <a href="https://github.com/ImAvgErix/ExoLauncher">Exo Launcher</a>
</p>

Exo Control gives AI agents **eyes and hands on a real Windows PC** — desktop UIA, browser DOM/CDP, files, registry, and OS infrastructure — without screenshot-first waste or silent destruction.

There is no cloud account, no telemetry, and no “claim full control” while ops are stubs. One agent holds a **desktop lease**; destructive work needs `confirm=true`.

| Surface | What you get |
|---------|----------------|
| **Desktop** | UIA-first click/type/fill, multi-window lease, multi-monitor bind, persistent UI memory |
| **Browser** | Chrome/Edge CDP + Exo WebView2: snapshot refs, DOM click/type, zero screenshots on the happy path |
| **OS** | Files (allowroot), registry, processes/services, fuzzy app launch → window ready |
| **Efficiency** | Compact observe (≤4KB / ≤40 refs), batched `aether_exec`, screenshots only on ask or structure miss |

Related product: **[Exo Launcher](https://github.com/ImAvgErix/ExoLauncher)** — the game library Exo Control is built to drive.

## Requirements

- Windows (primary)
- Python 3.10+

## Install

```bash
git clone https://github.com/ImAvgErix/ExoControl.git
cd ExoControl
pip install -e .
playwright install chromium
```

Preferred import: `exo_control` (re-exports). `aether.*` stays stable — see [docs/API-STABILITY.md](docs/API-STABILITY.md).  
CLI: `exo-control` (compat: `aether`).

**Live runtime path used by Grok/Cursor MCP:** copy or install so `PYTHONPATH` includes this package (often `%USERPROFILE%\.aether\aether-driver\src`).

## Cursor (MCP)

```json
{
  "mcpServers": {
    "exo-control": {
      "command": "python",
      "args": ["-m", "exo_control.slim_mcp_server"],
      "env": {
        "PYTHONPATH": "%USERPROFILE%\\.aether\\aether-driver\\src",
        "AETHER_PREFER_CUA": "0"
      }
    }
  }
}
```

Prefer **one batched** `aether_exec` script over chatty single clicks.

## Claude Desktop / any MCP host

Same server module: `exo_control.slim_mcp_server` (compat: `aether.slim_mcp_server`).

## CLI

```bash
exo-control --help
aether windows
aether lease status
aether script steps.json
```

## Python

```python
from exo_control.exec_engine import AetherExecEngine

eng = AetherExecEngine()
eng.execute([
    {"op": "lease_acquire", "agent_id": "my-agent", "task": "demo", "ttl_sec": 120},
    {"op": "launch", "app": "notepad"},          # fuzzy resolve + wait_ready
    {"op": "focus", "title": "Notepad", "monitor": 1},
    {"op": "type", "text": "hello from exo-control"},
    {"op": "notify", "title": "Exo Control", "body": "Done"},
    {"op": "lease_release"},
])
```

### Multi-monitor

```json
{"op": "focus", "title": "Exo Launcher", "monitor": 2}
{"op": "observe", "monitor": 2}
{"op": "screenshot", "title": "Exo Launcher", "monitor": 2}
```

Wrong-monitor bind fails closed (does not silently capture the other display).

### Persistent UI memory

Successful clicks are stored under `%USERPROFILE%\.aether\state\ui_memory.json`, keyed by query + process name (survives PID recycle). Misses invalidate the entry so agents do not keep hammering a renamed control.

## Safety

- Desktop lease: one agent holds the hands at a time
- Kill / registry write / service mutate / recursive delete require `confirm=true`
- Hard denies: anti-cheat tampering, credential dumping, silent elevation
- Details: [SECURITY.md](SECURITY.md)

## Docs

| Doc | Role |
|-----|------|
| [docs/JARVIS-OS.md](docs/JARVIS-OS.md) | Capability bar (Floor + P0 + P1) |
| [docs/JARVIS-PLUS.md](docs/JARVIS-PLUS.md) | Plus bar (STA, DOM loop, multi-window, presence) |
| [docs/CHARTER.md](docs/CHARTER.md) | Product charter |
| [docs/API-STABILITY.md](docs/API-STABILITY.md) | Import / op stability |
| [SECURITY.md](SECURITY.md) | Hard stops, lease, confirm gates |
| [CHANGELOG.md](CHANGELOG.md) | Releases |

## Status

**v1.0.0** — Jarvis OS complete (P0 + P1). Package `exo-control` with dual `exo_control` / `aether.*` imports. Voice listen remains experimental/cut (not required to live in the PC).

## License

MIT
