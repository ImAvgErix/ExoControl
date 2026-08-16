# Exo Control — live-in-the-PC model

Exo Control is the shared pair of **eyes and hands** on a Windows machine. Agents do not own the desktop; they **lease** it, act, then release. `session_open` is the remote-access shape of that lease: take the chair, drive the real cursor and keys, leave when done. In **Full-Trust**, the holder owns the desktop for the life of the lease (auto-renewed on hands) — still one lease, still a human kill-switch.

## Model

1. **Eyes (read-only)** — `windows`, `observe`/`read`, `eyes`, `eyes_read`/`look`, `cdp_discover`, `wait_cdp`, `status`, `stats`, `clipboard_get`, `apps`, `files_list` (inside roots), `search` / `search_content` (`provider=` on search), `scrape` / `files_convert` / `files_find` / `xlsx` / `rag` / `git` / `gh_pr` / `wiki` / `weather` / `hn` / `memory_*` / `recall` / `mail_list` / `todo` / `onenote` / `teams` / `notion` / `linear` / `contacts` / `whoami` / `disk` / `hash` / `tree` / `files_stat`, `browser_use` / `browser_use_start` (Browser Use Cloud; `BROWSER_USE_API_KEY`), `ego` (status only), Pilot (`goal` / `proof` / `changed` / `undo` / `skill_*` / `heal`), `os_info`, `trust_status`, `session_*` reads, `lease_*`, `help`. No lease required.
2. **Hands (mutating)** — click/type/scroll/scroll_into_view/hover/drag/hotkey/fill/focus/window_*/launch/open/screenshot/browser_*/web_task/clipboard_set/proc-kill/notify/files write. Require a valid desktop lease.

`lease_acquire` starts a live eyes loop (disable with `eyes:false` or `EXO_LIVE_EYES=0`). After hands, the step result includes a compact `seen` glance. Scroll is an aimed SendInput wheel on the document — never Home/End. Browser scroll hits the page (`window.scrollBy` / `scrollIntoView`), not chrome. `web_task` runs a multi-step web job as **one** leased step (structure/ref path; optional Browser Use extra).
3. **Exo Launcher / WebView2** — optional first-class target. Launch with CDP (`scripts/Launch-ExoWithCdp.ps1`), then `wait_cdp` / `cdp_discover` / browser ops. Control works without Exo Launcher.
4. **Session** — `remember` / `checkpoint` / `recover` persist prefs and last focus under `~/.exo/state/sessions/` so the machine feels like this agent's PC across process restarts.

## Desktop lease

- Lock: `%USERPROFILE%\.exo\locks\desktop.lock`
- State: `%USERPROFILE%\.exo\state\desktop_lease.json`
- `lease_acquire` → token (same `agent_id` renews)
- `lease_status` reports holder/task/expiry — **never the token**
- `session_open` / `seat` / `take_seat` — same lock, longer default TTL, eyes on, **never returns the token**. Holds across `execute()` calls until `session_close`
- `session_status` — seated / holder / task / expiry — **never the token**
- `pointer` / `mouse` / `keypress` / `drive` — raw SendInput HID (skip UIA). `drive` is a one-step burst: `[{"move":[x,y]},{"click":"left"},{"type":"hi"},{"key":"enter"}]`
- Steal only if expired, or `force_release` with token / holder / `EXO_ALLOW_FORCE_RELEASE=1` / Full-Trust
- Mutating steps need lease in-script or on the step
- Full-Trust auto-renews the lease after successful hands
- Tests: `EXO_LOCK_DIR` / `EXO_STATE_DIR` (legacy `AETHER_*` still read)

This is **not** an RDP/VNC pixel stream. The agent is in the chair: real cursor, real keys, live eyes.

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

Destructive OS ops need `confirm=true` unless Full-Trust is enabled. Files stay inside allowroots (Full-Trust adds user-profile roots only). Kill file: `~/.exo/KILL`. See [SECURITY.md](../SECURITY.md).
