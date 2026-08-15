---
name: exo-control
description: Use when any AI needs eyes and hands on Windows — desktop UIA, browser CDP, files, registry, OS ops via Exo Control (MCP, CLI, or Python). Harness-agnostic.
---

# Exo Control (any AI · any harness)

Hardened PC control plane. Not tied to Cursor, Grok, Claude, or Codex — those are just hosts.

## Surfaces (in priority order for agents)

1. **MCP**: `exo_exec` / `exo_screenshot` / `exo_help`
2. **CLI**: `exo-control exec` or `exo-control script steps.json`
3. **Python**: `from exo_control import ExoExecEngine`

Server: `python -m exo_control.slim_mcp_server`  
Install: `pip install "git+https://github.com/ImAvgErix/ExoControl.git@v2.2.0"` (or `pip install -e .`).  
Env: `EXO_PREFER_CUA=0`. State under `~/.exo/`. `PERPLEXITY_API_KEY` unlocks `search`. `BROWSER_USE_API_KEY` unlocks `browser_use`. `FIRECRAWL_API_KEY` unlocks `scrape`. Local `files_convert` / `files_find` / `memory_*` work without cloud keys.

## Rules

1. Script-first — one batched exec, not click spam.
2. `lease_acquire` before hands; `lease_release` after.
3. Structure first (observe/read/verify); screenshot only on miss or explicit ask.
4. `{"op":"help"}` or `exo_help` if unsure of ops.
5. `confirm=true` for destructive OS ops; never kill anti-cheat.
6. Multi-monitor: pass `monitor` on focus/observe/shot; wrong display fails closed.

## Web search (not UI find)

Lease-free Perplexity Search as Code. Fan out queries, then filter / dedupe / rank in the result. Requires `PERPLEXITY_API_KEY`. Do **not** open a browser to look something up.

```json
{"op": "search", "query": ["rust async runtimes", "tokio vs async-std"], "max": 5, "dedupe": true}
{"op": "search_content", "query": "installation", "urls": ["https://docs.rs/tokio"]}
```

## Browser Use Cloud

Hosted web agent or a managed Chromium you drive with existing `browser_*` ops. Requires `BROWSER_USE_API_KEY`. Exo Control is Windows-only; this is the remote browser path.

```json
{"op": "browser_use", "task": "Find the top Show HN post"}
{"op": "browser_use_start", "country": "us"}
{"op": "browser_connect", "provider": "browser-use"}
```

## ego lite

`{"op":"ego"}` only. ego lite has no Windows app. Use `browser_*` spaces on this machine.

## Other lease-free addons

```json
{"op": "scrape", "url": "https://example.com"}
{"op": "files_convert", "path": "C:/Users/you/.exo/workspace/notes.docx"}
{"op": "files_find", "query": "Q3-forecast"}
{"op": "memory_add", "text": "Prefers dark mode"}
{"op": "recall", "query": "standup"}
{"op": "mail_list", "max": 5}
```

## Minimal script

```json
[
  {"op": "lease_acquire", "agent_id": "agent", "task": "demo", "ttl_sec": 120},
  {"op": "launch", "app": "notepad"},
  {"op": "type", "text": "hello"},
  {"op": "lease_release"}
]
```

## Docs in repo

- `AGENTS.md` — drop into any agent context
- `docs/HARNESS.md` — install for every host
- `docs/CAPABILITY.md` — capability bar
- `SECURITY.md` — hard stops
