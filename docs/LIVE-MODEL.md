# Exo Control — live-in-the-PC model

Exo Control is the shared pair of **eyes and hands** on a Windows machine. Agents do not own the desktop; they **lease** it, act, then release.

## Model

1. **Eyes (read-only)** — `windows`, `observe`/`read`, `eyes`, `eyes_read`/`look`, `cdp_discover`, `wait_cdp`, `status`, `stats`, `clipboard_get`, `apps`, `files_list` (inside roots), `search` / `search_content` (`provider=` on search), `scrape` / `files_convert` / `files_find` / `xlsx` / `rag` / `git` / `gh_pr` / `wiki` / `weather` / `hn` / `memory_*` / `recall` / `mail_list` / `todo` / `onenote` / `teams` / `notion` / `linear` / `contacts` / `whoami` / `disk` / `hash` / `tree` / `files_stat`, `browser_use` / `browser_use_start` (Browser Use Cloud; `BROWSER_USE_API_KEY`), `ego` (status only), Pilot (`goal` / `proof` / `changed` / `undo` / `skill_*` / `heal`), `lease_*`, `help`. No lease required.
2. **Hands (mutating)** — click/type/scroll/scroll_into_view/hover/drag/hotkey/fill/focus/window_*/launch/open/screenshot/browser_*/clipboard_set/proc-kill/notify. Require a valid desktop lease.

`lease_acquire` starts a live eyes loop (disable with `eyes:false` or `EXO_LIVE_EYES=0`). After hands, the step result includes a compact `seen` glance. Scroll is an aimed SendInput wheel on the document — never Home/End. Browser scroll hits the page (`window.scrollBy` / `scrollIntoView`), not chrome.
3. **Exo Launcher / WebView2** — optional first-class target. Launch with CDP (`scripts/Launch-ExoWithCdp.ps1`), then `wait_cdp` / `cdp_discover` / browser ops. Control works without Exo Launcher.

## Desktop lease

- Lock: `%USERPROFILE%\.exo\locks\desktop.lock`
- State: `%USERPROFILE%\.exo\state\desktop_lease.json`
- `lease_acquire` → token (same `agent_id` renews)
- `lease_status` reports holder/task/expiry — **never the token**
- Steal only if expired, or `force_release` with token / holder / `EXO_ALLOW_FORCE_RELEASE=1`
- Mutating steps need lease in-script or on the step
- Tests: `EXO_LOCK_DIR` / `EXO_STATE_DIR` (legacy `AETHER_*` still read)

## Surfaces

| Surface | Entry |
|---------|--------|
| MCP | `python -m exo_control.slim_mcp_server` |
| CLI | `exo-control exec` / `script` / `ops` |
| Python | `from exo_control import ExoExecEngine` |

Self-describe: `{"op":"help"}` or MCP `exo_help`. Full host matrix: [HARNESS.md](HARNESS.md).

## Multi-agent etiquette

1. Acquire lease with a clear `task` string.
2. Focus → act → verify in one batched script when possible.
3. Renew on long jobs; always release when done.
4. Never fight an active holder — wait or coordinate out-of-band.

## Safety

Destructive OS ops need `confirm=true`. Files stay inside allowroots. See [SECURITY.md](../SECURITY.md).
