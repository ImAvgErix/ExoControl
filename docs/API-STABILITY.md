# API stability (v2.x)

2.2 is additive: `search` / `search_web` / `search_content` (Perplexity), `browser_use` / `browser_use_start` / `browser_use_stop` (Browser Use Cloud), `ego` (honest status), plus lease-free addons (`scrape` / `crawl` / `site_map`, `files_convert`, `stagehand` / `browser_act`, `skyvern`, `omni`, `agentql`, `files_find`, `memory_add` / `memory_search`, `composio` / `mail_list` / `cal_next` / `drive_get`, `recall`, Wave 1 `xlsx` / `todo` / `onenote` / `teams` / `mail_send` / `read_url` / `git` / `gh_pr` / `volume` / `winget` / `recycle` / `eventlog` / `ocr_win` / `stt` / `tts`, Wave 2 `docling` / `rag` / `winsearch` / `steel_start` / `tavily` / `exa` / `slack` / `notion` / `linear` / `pwsh` / `wsl` / `docker` / `print` / `wifi` / `power` / `disk` / `whoami` / `certs` / `hash` / `lnk` / `dialog`). Leased extras: `window_move`, `browser_network` / `browser_downloads` / `browser_pdf` / `browser_tabs`. Existing op names stay. Remote CDP is still denied except Browser Use (API key) or `EXO_ALLOW_REMOTE_CDP=1`. `browser_act` / `browser_query` / `browser_extract` are HTTP aliases and do **not** require a desktop lease.

2.1 is additive: `scroll_into_view`, `hover`, `eyes_read`/`look`/`glance`, `browser_scroll_into_view`, `browser_hover`, and `seen` on hand results. Existing op names stay.

## Stable

- Python: `import exo_control` / `from exo_control import ExoExecEngine` (**preferred**)
- Python: `import aether` and `aether.*` (**compat shim** — implementation is `exo_control`)
- Python: `AetherExecEngine` is an alias of `ExoExecEngine`
- CLI: `exo-control` (preferred); `aether` entry point still works
- MCP tools: `exo_exec` / `exo_screenshot` / `exo_help`. `aether_*` only when `EXO_MCP_ALIASES=1`
- MCP op names: existing ops remain; additive fields only
- 1.3 honesty: `lease_status` no longer returns `token`; files `confirm` no longer escapes allowroots

## State directories

| Path | Role |
|------|------|
| `~/.exo/` | **Preferred** product root |
| `~/.exo/state` | lease focus, UI memory, audits |
| `~/.exo/locks` | desktop lease lock |
| `~/.exo/workspace` | default file allowroot |
| `~/.aether/` | **Legacy** — still read / soft-migrated |

Env (preferred → legacy):

- `EXO_HOME` / `AETHER_HOME`
- `EXO_STATE_DIR` / `AETHER_STATE_DIR`
- `EXO_LOCK_DIR` / `AETHER_LOCK_DIR`
- `EXO_FILE_ROOTS` / `AETHER_FILE_ROOTS`
- `EXO_PREFER_CUA` / `AETHER_PREFER_CUA` (prefer_cua)

## Result envelope

Every `ExoExecEngine.execute` step result is a **dict** with `ok: bool`.  
`windows` always returns `{ok, windows, count}` (never a bare list).

## Document text

`read` / `observe` expose document body via UIA Value/Text patterns and Win32
edit `WM_GETTEXT` when needed. Clipboard select-all/copy is **last resort** and
flagged as `via: "clipboard"`.

## Physical package layout

Implementation folder is `src/exo_control/`. `src/aether/` is a shim. Do not break `aether.*` imports in 2.x patches.
