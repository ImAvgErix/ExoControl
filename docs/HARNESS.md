# Any AI · Any harness

Exo Control is a **control plane**, not a Cursor plugin. Give it to Grok, Claude, GPT, Gemini, local models, or a custom agent — same surface.

Three ways in (pick what the host supports):

| Surface | When to use | Entry |
|---------|-------------|--------|
| **MCP (stdio)** | Host has MCP tools | `python -m exo_control.slim_mcp_server` |
| **CLI** | Host can run shell / tools | `exo-control exec` / `script` |
| **Python** | In-process agent / notebook | `ExoExecEngine().execute([...])` |

All three hit the **same** exec engine, lease, safety gates, and ops.

## Agent rules (copy into any system prompt)

```
You control a Windows PC via Exo Control.
- Prefer one batched script over many single clicks.
- Mutating work: lease_acquire → act → lease_release.
- Eyes first: windows / observe / read / verify. Screenshots only if structure fails.
- Scroll with scroll / scroll_into_view / browser_scroll. Never Home/End.
- Call help (or MCP exo_help) before inventing ops.
- confirm=true for destructive OS ops. Never kill anti-cheat.
- Compact responses by default; do not dump raw HTML/trees unless verbose.
- Web facts: search (provider=perplexity|tavily|exa|ddg|serper|brave). Page markdown: scrape (provider=firecrawl|jina). Cloud browser: browser_use (BROWSER_USE_API_KEY). Page UI: browser_*.
- Docs on disk: files_convert (engine=markitdown|docling) / files_find / xlsx / rag / zip / sqlite. Memory: memory_add / memory_search. History: recall (Screenpipe). Graph: todo / onenote / teams / mail_send / cal_add. git / gh_pr. Wiki/weather/hn stay their own ops. SaaS: slack / notion / linear / jira.
- Exo Control is Windows-only. ego lite has no Windows app.
```

## MCP tools (all hosts)

| Tool | Alias | Role |
|------|-------|------|
| `exo_exec` | `aether_exec` | JSON step script |
| `exo_screenshot` | `aether_screenshot` | Pixels when needed |
| `exo_help` | `aether_help` | Op catalog + rules |

`script` accepts: JSON array, JSON string, or `{"steps":[...]}`.

### Generic MCP config (stdio)

```json
{
  "mcpServers": {
    "exo-control": {
      "command": "python",
      "args": ["-m", "exo_control.slim_mcp_server"],
      "env": {
        "EXO_PREFER_CUA": "0"
      }
    }
  }
}
```

Use the Python that has the package installed (`pip install -e .` from the repo). Prefer **not** setting `PYTHONPATH` to a second checkout — dual trees shadow each other. Run `exo-control doctor` if imports look wrong.

### Cursor

`~/.cursor/mcp.json` or project `.cursor/mcp.json` — same block as above.

### Claude Desktop

`claude_desktop_config.json` → `mcpServers` — same block. Restart Claude Desktop.

### Claude Code / Codex / other CLI agents

Register the MCP server per host docs, or skip MCP and use CLI:

```bash
exo-control exec --steps "[{\"op\":\"help\"}]"
exo-control script workflow.json
```

### Windsurf / Continue / Cline / VS Code MCP

Any host that launches a **stdio MCP** process: same `command` + `args` + `env`.

### No MCP? Pipe JSON

```bash
echo '[{"op":"lease_status"}]' | exo-control exec
# or
exo-control exec -f steps.json
```

### Python (any framework)

```python
from exo_control import ExoExecEngine

eng = ExoExecEngine()
result = eng.execute([
    {"op": "help", "query": "launch"},
    {"op": "lease_acquire", "agent_id": "my-bot", "task": "demo", "ttl_sec": 90},
    {"op": "launch", "app": "notepad"},
    {"op": "lease_release"},
])
print(result["ok"], result["steps"][-1]["result"])
```

## Self-describe (so you never hardcode the catalog)

```json
{"op": "help"}
{"op": "help", "query": "browser", "detail": true}
{"op": "capabilities"}
```

Or MCP: `exo_help` with optional `query`.

## Minimal happy path

```json
[
  {"op": "lease_acquire", "agent_id": "any-agent", "task": "demo", "ttl_sec": 120},
  {"op": "launch", "app": "notepad"},
  {"op": "focus", "title": "Notepad"},
  {"op": "type", "text": "hello from any harness"},
  {"op": "notify", "title": "Exo Control", "body": "Done"},
  {"op": "lease_release"}
]
```

## Safety (same for every model)

- One **desktop lease** at a time
- Destructive / kill / registry write / service control need `confirm=true`
- Hard deny: anti-cheat, credential dump, silent elevation
- Details: [SECURITY.md](../SECURITY.md)

## Install once

```bash
pip install "git+https://github.com/ImAvgErix/ExoControl.git@v2.2.0"
exo-control doctor
# optional CDP:
pip install "exo-control[browser]"
playwright install chromium
```

Do **not** set `PYTHONPATH` to `~\.aether\aether-driver` or `Documents\exo-control` — those shadow the installed package.

## Versioning

Exo Control is a **library**. Version is in `pyproject.toml`. Wheels may ship as GitHub Release assets; there is no Setup.exe. Binary installers live on [Exo Launcher](https://github.com/ImAvgErix/ExoLauncher) only.
