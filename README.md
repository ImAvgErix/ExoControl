<p align="center"><strong>Exo Control</strong></p>

<h1 align="center">Realtime PC eyes and hands for any AI agent</h1>

<p align="center">
  Any model · MCP · CLI · Python<br/>
  Compact. Leased. Honest.
</p>

<p align="center">
  <a href="LICENSE"><img alt="MIT license" src="https://img.shields.io/github/license/ImAvgErix/ExoControl?style=flat-square&color=111111" /></a>
  <a href="https://pypi.org/project/exo-control/"><img alt="PyPI" src="https://img.shields.io/pypi/v/exo-control?style=flat-square&color=111111" /></a>
  <a href="docs/HARNESS.md"><img alt="Any harness" src="https://img.shields.io/badge/harness-MCP%20%7C%20CLI%20%7C%20Python-79f2c0?style=flat-square" /></a>
</p>

<p align="center">
  <a href="#install"><strong>Install</strong></a>
  ·
  <a href="AGENTS.md">Agent instructions</a>
  ·
  <a href="SECURITY.md">Safety</a>
  ·
  <a href="https://github.com/ImAvgErix/ExoLauncher">Exo Launcher</a>
</p>

**Exo Control** is a Windows Python library that gives any AI eyes and hands on the desktop. Same ops over MCP, CLI, or Python. Not an app and not a Setup.exe — install with `pip`.

| How the AI talks | Entry |
|------------------|--------|
| **MCP** | `exo_exec` · `exo_screenshot` · `exo_help` |
| **CLI** | `exo-control exec` · `exo-control script` · `exo-control doctor` |
| **Python** | `from exo_control import ExoExecEngine` |

Works with [Exo Launcher](https://github.com/ImAvgErix/ExoLauncher) when it is installed. Not required.

## Install

```bash
pip install exo-control
exo-control doctor
```

Optional browser CDP: `pip install "exo-control[browser]"` then `playwright install chromium`.

Pin: `pip install "exo-control==2.2.0"` or `pip install "git+https://github.com/ImAvgErix/ExoControl.git@v2.2.0"`.

State lives under `~/.exo/`. Legacy `~/.aether/` is migrated automatically.

## MCP

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

Do not set `PYTHONPATH` at a second tree. `exo-control doctor` reports shadowing.

## Quick script

```bash
exo-control script examples/notepad.json
```

```python
from exo_control import ExoExecEngine

ExoExecEngine().execute({
    "steps": [
        {"op": "lease_acquire", "agent_id": "demo", "task": "notepad", "ttl_sec": 90},
        {"op": "launch", "app": "notepad"},
        {"op": "type", "text": "hello from Exo Control"},
        {"op": "verify", "text": "hello from Exo Control"},
    ],
    "finally": [
        {"op": "window_close", "title": "Notepad", "discard_unsaved": True},
        {"op": "lease_release"},
    ],
})
```

Failed steps do not attach screenshots unless `screenshot_on_fail: true`. Use `{"op":"last_error"}`. Drop [AGENTS.md](AGENTS.md) into any model's rules.

## What it can do

| Surface | Ops |
|---------|-----|
| **Desktop** | UIA click/type/fill, aimed wheel + `scroll_into_view` + hover, live eyes, lease, multi-monitor |
| **Browser** | CDP snapshot refs, DOM click/type, page `scrollBy` / `scrollIntoView` |
| **OS** | Allowrooted files, HKCU registry, processes/services, fuzzy launch |
| **Search** | Lease-free `search` (`provider=perplexity\|tavily\|exa\|ddg\|serper\|brave`) + `search_content` |
| **Cloud browser** | Browser Use `browser_use` / `browser_use_start` (`BROWSER_USE_API_KEY`) |
| **Web extract** | `scrape` (`provider=firecrawl\|jina`); `crawl` / `site_map`; Stagehand `browser_act`; Skyvern; AgentQL |
| **Docs / find** | `files_convert` (`engine=markitdown\|docling`), `files_find` (Everything or walk) |
| **Memory / history** | `memory_add` / `memory_search` (local or Mem0); `recall` (Screenpipe) |
| **Mail / calendar** | `mail_list` / `cal_next` / `drive_get` / `todo` / `onenote` / `teams` / `mail_send` (Graph or Composio) |
| **Desk extras** | `xlsx`, `git`, `gh_pr`, `volume`, `winget`, `recycle`, `eventlog`, `window_move`, `browser_network` / `pdf` / `tabs` |
| **Wave 2** | `rag` / `steel_start` / `slack` / `notion` / `linear` / `pwsh` / `docker` / `hash` / `whoami` / `disk` |
| **Waves 3–5** | Graph writes, CDP extras, `wiki`/`weather`/`hn`, Jira/Discord/Airtable, `zip`/`sqlite`/`tree`, `which`/`dns`/`lock_pc` |
| **Pilot** | Original layer: `goal` / `checkpoint` / `proof` / `changed` / `undo` / `skill_save` / `skill_run` / `heal` |

`{"op":"help"}` lists the core ops. `detail=true` is the full catalog.

## Safety

- One desktop lease; `lease_status` never returns the token
- Destructive OS ops need `confirm=true` (agent assertion, not a human prompt)
- Files stay in `EXO_FILE_ROOTS` unless the operator sets `EXO_ALLOW_OUTSIDE_ROOTS=1`
- Hard denies: anti-cheat, unnamed PID kill, critical services, non-loopback CDP
- [SECURITY.md](SECURITY.md)

## Docs

| Doc | Role |
|-----|------|
| [AGENTS.md](AGENTS.md) | Drop-in agent instructions |
| [docs/HARNESS.md](docs/HARNESS.md) | Host install matrix |
| [docs/LIVE-MODEL.md](docs/LIVE-MODEL.md) | Lease / eyes / hands |
| [docs/API-STABILITY.md](docs/API-STABILITY.md) | 2.0 public surface |
| [CHANGELOG.md](CHANGELOG.md) | Version history |

## License

MIT
