<p align="center">
  <strong>Exo Control</strong>
</p>

<h1 align="center">Realtime PC eyes and hands for any AI agent</h1>

<p align="center">
  Any model · any harness · MCP · CLI · Python<br/>
  Compact. Leased. Honest. Jarvis OS complete.
</p>

<p align="center">
  <a href="https://github.com/ImAvgErix/ExoControl/releases/latest"><img alt="Latest release" src="https://img.shields.io/github/v/release/ImAvgErix/ExoControl?style=flat-square&label=release&color=79f2c0" /></a>
  <a href="LICENSE"><img alt="MIT license" src="https://img.shields.io/github/license/ImAvgErix/ExoControl?style=flat-square&color=111111" /></a>
  <a href="docs/HARNESS.md"><img alt="Any harness" src="https://img.shields.io/badge/harness-MCP%20%7C%20CLI%20%7C%20Python-79f2c0?style=flat-square" /></a>
  <a href="docs/JARVIS-OS.md"><img alt="Jarvis OS" src="https://img.shields.io/badge/Jarvis%20OS-complete-79f2c0?style=flat-square" /></a>
</p>

<p align="center">
  <a href="#install"><strong>Install</strong></a>
  ·
  <a href="docs/HARNESS.md">Any harness</a>
  ·
  <a href="AGENTS.md">Agent instructions</a>
  ·
  <a href="SECURITY.md">Safety</a>
  ·
  <a href="https://github.com/ImAvgErix/ExoLauncher">Exo Launcher</a>
</p>

Exo Control is a **harness-agnostic control plane**. Hand it to Grok, Claude, GPT, Gemini, a local model, or your own agent loop — they all use the same ops.

| How the AI talks | Entry |
|------------------|--------|
| **MCP tools** | `exo_exec` · `exo_screenshot` · `exo_help` (aliases `aether_*`) |
| **CLI / shell tools** | `exo-control exec` · `exo-control script` |
| **Python in-process** | `AetherExecEngine().execute([...])` |

Not a single-vendor plugin. Cursor, Claude Desktop, Claude Code, Codex, Windsurf, Continue, Cline, custom stdio clients — same server.

Related app: **[Exo Launcher](https://github.com/ImAvgErix/ExoLauncher)** (optional first-class target; Control works without it).

## Requirements

- Windows (primary)
- Python 3.10+

## Install

```bash
git clone https://github.com/ImAvgErix/ExoControl.git
cd ExoControl
pip install -e .
playwright install chromium
exo-control ops
```

Preferred import: `exo_control`. Compat: `aether.*` — [docs/API-STABILITY.md](docs/API-STABILITY.md).

## Give it to any AI

### 1) MCP (most chat agents)

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

Paste into Cursor, Claude Desktop, or any stdio MCP host. Full host matrix: **[docs/HARNESS.md](docs/HARNESS.md)**.

Tools the model sees:

| Tool | What it does |
|------|----------------|
| `exo_exec` | Run a JSON step script (batch workflows) |
| `exo_screenshot` | Pixels only when structure fails |
| `exo_help` | Self-describe ops + rules (no guessing) |

### 2) CLI (any agent that can run a command)

```bash
exo-control exec --steps "[{\"op\":\"help\"}]"
exo-control script workflow.json
echo "[{\"op\":\"lease_status\"}]" | exo-control exec
exo-control mcp          # run MCP server on stdio
```

### 3) Python (custom harness)

```python
from exo_control.exec_engine import AetherExecEngine

eng = AetherExecEngine()
eng.execute([
    {"op": "lease_acquire", "agent_id": "my-agent", "task": "demo", "ttl_sec": 120},
    {"op": "launch", "app": "notepad"},
    {"op": "type", "text": "hello from any harness"},
    {"op": "notify", "title": "Exo Control", "body": "Done"},
    {"op": "lease_release"},
])
```

### Drop-in agent context

Copy **[AGENTS.md](AGENTS.md)** into the system prompt / project rules of whatever model you use. Skill package: [`skills/exo-control/SKILL.md`](skills/exo-control/SKILL.md).

## What it can do

| Surface | Ops |
|---------|-----|
| **Desktop** | UIA click/type/fill, multi-window lease, multi-monitor bind, persistent UI memory |
| **Browser** | CDP snapshot refs, DOM click/type, Exo WebView2 |
| **OS** | Files (allowroot), registry, processes/services, fuzzy launch → window ready |
| **Efficiency** | Compact observe, batched exec, no screenshot-default |

Self-describe at runtime: `{"op":"help","detail":true}` or MCP `exo_help`.

## Safety

- One desktop **lease** at a time
- Kill / registry write / service mutate / recursive delete need `confirm=true`
- Hard denies: anti-cheat, credential dump, silent elevation
- [SECURITY.md](SECURITY.md)

## Docs

| Doc | Role |
|-----|------|
| [docs/HARNESS.md](docs/HARNESS.md) | **Any AI · any host** install + rules |
| [AGENTS.md](AGENTS.md) | Drop-in instructions for the model |
| [docs/JARVIS-OS.md](docs/JARVIS-OS.md) | Capability bar |
| [docs/CHARTER.md](docs/CHARTER.md) | Product charter |
| [CHANGELOG.md](CHANGELOG.md) | Releases |

## Status

**v1.0.1** — Jarvis OS complete + harness-agnostic surface (self-describe help, dual tool names, multi-host docs). Voice listen remains experimental/cut.

## License

MIT
