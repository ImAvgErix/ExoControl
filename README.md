<p align="center">
  <strong>Exo Control</strong>
</p>

<h1 align="center">Realtime PC eyes and hands for any AI agent</h1>

<p align="center">
  Any model · any harness · MCP · CLI · Python<br/>
  Compact. Leased. Honest.
</p>

<p align="center">
  <a href="LICENSE"><img alt="MIT license" src="https://img.shields.io/github/license/ImAvgErix/ExoControl?style=flat-square&color=111111" /></a>
  <a href="docs/HARNESS.md"><img alt="Any harness" src="https://img.shields.io/badge/harness-MCP%20%7C%20CLI%20%7C%20Python-79f2c0?style=flat-square" /></a>
  <a href="docs/CAPABILITY.md"><img alt="Capability" src="https://img.shields.io/badge/capability-bar-79f2c0?style=flat-square" /></a>
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

**Exo Control** is a harness-agnostic **Python library** that gives AI agents eyes and hands on Windows. Hand it to any model via MCP, CLI, or Python — same ops.

This is **not** a desktop app and does **not** ship a Setup.exe. Install with `pip` (or `PYTHONPATH`). Binary releases belong on [Exo Launcher](https://github.com/ImAvgErix/ExoLauncher), not here.

| How the AI talks | Entry |
|------------------|--------|
| **MCP tools** | `exo_exec` · `exo_screenshot` · `exo_help` (compat aliases `aether_*`) |
| **CLI / shell** | `exo-control exec` · `exo-control script` · `exo-control doctor` |
| **Python** | `ExoExecEngine().execute([...])` |

Related product: **[Exo Launcher](https://github.com/ImAvgErix/ExoLauncher)** — optional first-class target; Control works without it.

## Requirements

- Windows (primary)
- Python 3.10+

## Install

**One-liner (recommended):**

```bash
pip install "git+https://github.com/ImAvgErix/ExoControl.git"
playwright install chromium
exo-control doctor
```

When published to PyPI:

```bash
pip install exo-control
```

**Editable clone (development):**

```bash
git clone https://github.com/ImAvgErix/ExoControl.git
cd ExoControl
pip install -e ".[dev]"
playwright install chromium
exo-control ops
```

State lives under **`~/.exo/`** (locks, state, workspace). Legacy `~/.aether/` is migrated/read automatically.

Preferred import: `from exo_control import ExoExecEngine`. Technical compat: `aether.*` / `AetherExecEngine` — [docs/API-STABILITY.md](docs/API-STABILITY.md).

## Give it to any AI

### MCP

```json
{
  "mcpServers": {
    "exo-control": {
      "command": "python",
      "args": ["-m", "exo_control.slim_mcp_server"],
      "env": {
        "AETHER_PREFER_CUA": "0"
      }
    }
  }
}
```

After `pip install -e .`, **do not** set `PYTHONPATH` to a second tree (e.g. `~\.aether\aether-driver\src`) — leftover editable installs will shadow this package. Diagnose with `exo-control doctor`.

Paste into any stdio MCP host. Host matrix: **[docs/HARNESS.md](docs/HARNESS.md)**.

| Tool | Role |
|------|------|
| `exo_exec` | Batched JSON step script |
| `exo_screenshot` | Pixels only when structure fails |
| `exo_help` | Op catalog (self-describe) |

### CLI

```bash
exo-control exec --steps "[{\"op\":\"help\"}]"
exo-control script workflow.json
echo "[{\"op\":\"lease_status\"}]" | exo-control exec
```

### Python

```python
from exo_control import ExoExecEngine

eng = ExoExecEngine()
eng.execute([
    {"op": "lease_acquire", "agent_id": "my-agent", "task": "demo", "ttl_sec": 120},
    {"op": "launch", "app": "notepad"},
    {"op": "type", "text": "hello from Exo Control"},
    {"op": "window_close", "title": "Notepad"},  # Don't Save by default
    {"op": "lease_release"},
])
```

### Acceptance

```bash
# unit + doctor + CDP live (skips cleanly if no debugger)
pwsh -File scripts/Prove-Acceptance.ps1
python scripts/accept_cdp_live.py
# always-on: launches Chromium with remote debugging
python scripts/accept_cdp_chromium.py
```

### Agent reliability (1.2)

```json
{
  "steps": [
    {"op": "lease_acquire", "agent_id": "bot", "task": "ui", "ttl_sec": 120},
    {"op": "launch", "app": "notepad"},
    {"op": "read"},
    {"op": "click", "ref": "e0"},
    {"op": "type", "text": "hello"},
    {"op": "verify", "text": "hello"}
  ],
  "finally": [
    {"op": "window_close", "title": "Notepad"},
    {"op": "lease_release"}
  ]
}
```

Failed steps include `fail_screenshot` by default. Inspect with `{"op":"last_error"}`.

Drop **[AGENTS.md](AGENTS.md)** into any model’s system/project rules. Skill: [`skills/exo-control/SKILL.md`](skills/exo-control/SKILL.md).

## What it can do

| Surface | Ops |
|---------|-----|
| **Desktop** | UIA click/type/fill, multi-window lease, multi-monitor, UI memory |
| **Browser** | CDP snapshot refs, DOM click/type, Exo WebView2 |
| **OS** | Files (allowroot), registry, processes/services, fuzzy launch |
| **Efficiency** | Compact observe, batched exec, no screenshot-default |

Self-describe: `{"op":"help","detail":true}` or MCP `exo_help`. Full bar: [docs/CAPABILITY.md](docs/CAPABILITY.md).

## Safety

- One desktop **lease** at a time
- Kill / registry write / service mutate / recursive delete need `confirm=true`
- Hard denies: anti-cheat, credential dump, silent elevation
- [SECURITY.md](SECURITY.md)

## Docs

| Doc | Role |
|-----|------|
| [docs/HARNESS.md](docs/HARNESS.md) | Any AI · any host |
| [AGENTS.md](AGENTS.md) | Drop-in agent instructions |
| [docs/CAPABILITY.md](docs/CAPABILITY.md) | Capability bar |
| [docs/CHARTER.md](docs/CHARTER.md) | Product charter |
| [docs/LIVE-MODEL.md](docs/LIVE-MODEL.md) | Lease / eyes / hands model |
| [CHANGELOG.md](CHANGELOG.md) | Version history (git; no binary release assets) |

## License

MIT
