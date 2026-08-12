# Exo Control — live-in-the-PC model

Exo Control is the shared pair of **eyes and hands** on a Windows machine. Agents do not own the desktop; they **lease** it, act, then release.

## Model

1. **Eyes (read-only)** — `windows`, `observe`/`read`, `eyes`, `cdp_discover`, `wait_cdp`, `status`, `stats`, `clipboard_get`, `apps`, `files_list`, `lease_*`, `help`. No lease required.
2. **Hands (mutating)** — click/type/scroll/drag/hotkey/fill/focus/window_*/launch/open/screenshot/browser_*/clipboard_set/proc-kill. Require a valid desktop lease.
3. **Exo Launcher / WebView2** — optional first-class target. Launch with CDP (`scripts/Launch-ExoWithCdp.ps1`), then `wait_cdp` / `cdp_discover` / browser ops. Control works without Exo Launcher.

## Desktop lease

- Lock: `%USERPROFILE%\.aether\locks\desktop.lock`
- State: `%USERPROFILE%\.aether\state\desktop_lease.json`
- `lease_acquire` → token; **steal only if expired**
- Mutating steps need lease in-script or on the step
- Tests: `AETHER_LOCK_DIR` / `AETHER_STATE_DIR`

## Surfaces

| Surface | Entry |
|---------|--------|
| MCP | `python -m exo_control.slim_mcp_server` |
| CLI | `exo-control exec` / `script` / `ops` |
| Python | `from exo_control.exec_engine import AetherExecEngine` |

Self-describe: `{"op":"help"}` or MCP `exo_help`. Full host matrix: [HARNESS.md](HARNESS.md). Op catalog: [ACCEPTANCE.md](ACCEPTANCE.md) + runtime help.

## Multi-agent etiquette

1. Acquire lease with a clear `task` string.
2. Focus → act → verify in one batched script when possible.
3. Renew on long jobs; always release when done.
4. Never fight an active holder — wait or coordinate out-of-band.

## Safety

Destructive OS ops need `confirm=true`. Hard denies: anti-cheat, credential dump, silent elevation. See [SECURITY.md](../SECURITY.md).
