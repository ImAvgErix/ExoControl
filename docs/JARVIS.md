# Jarvis — live-in-the-PC model (Aether 1.7)

Aether is the shared pair of eyes and hands on this Windows machine. Agents do
not own the desktop; they **lease** it, act, then release.

## Live-in-PC model

1. **Eyes (read-only)** — `windows`, `observe`/`read`, `eyes`, `cdp_discover`,
   `wait_cdp`, `status`, `stats`, `clipboard_get`, `apps`, `files_list`,
   `lease_*`. No lease required.
2. **Hands (mutating)** — click/type/scroll/drag/hotkey/fill/focus/window_*/
   launch/open/screenshot/shot/browser_*/clipboard_set/proc-kill/desktop-switch. Require a
   valid desktop lease token.
3. **Exo / WebView2** — launch via `scripts/Launch-ExoWithCdp.ps1` (sets
   `EXO_CDP`, `EXO_CDP_PORT`, `WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS`). Then
   `wait_cdp` / `cdp_discover` / `eyes` for DOM endpoints.

## Desktop lease rules

- Lock file: `%USERPROFILE%\.aether\locks\desktop.lock` (Windows `msvcrt` exclusive).
- Lease JSON: `%USERPROFILE%\.aether\state\desktop_lease.json`.
- `lease_acquire(agent, task, ttl_sec=120)` → `{ok, token, expires_at}` or
  `{ok:false, holder, task, expires_at}` if another agent holds a non-expired lease.
- **Steal only if expired.** Never preempt an active holder.
- `lease_renew(token, ttl_sec)` / `lease_release(token)` / `lease_status()`.
- Mutating exec steps accept `step.lease` **or** a token acquired earlier in the
  **same** `execute()` script. Otherwise: `{ok:false, error:"desktop lease required"}`.
- Tests override dirs with `AETHER_LOCK_DIR` / `AETHER_STATE_DIR`.

CLI:

```
aether cdp
aether lease status
aether lease acquire --agent grok --task "focus exo"
aether lease release --token TOKEN
```

## Op catalog (exec)

| op | lease? | purpose |
|----|--------|---------|
| `status` / `stats` | no | driver health / metrics |
| `windows` / `list_windows` | no | top-level windows |
| `observe` / `compact_observe` / `read` | no | UI tree / OCR compact view |
| `eyes` | no | compact_observe + CDP endpoint summary |
| `cdp` / `cdp_discover` | no | discover DevTools endpoints |
| `wait_cdp` / `wait_for_cdp` | no | poll CDP until up (`timeout`, `port`) |
| `clipboard_get` | no | read clipboard text |
| `apps` | no | running apps pid/title/exe |
| `files_list` | no | non-recursive capped directory listing |
| `lease_acquire` / `lease_renew` / `lease_release` / `lease_force_release` / `lease_status` | no | desktop lease |
| `focus` / `smart_focus` | **yes** | foreground a window |
| `click` / `type` / `scroll` / `drag` / `hotkey` / `keys` / `fill` | **yes** | hands |
| `window_*` / `window` | **yes** | min/max/restore/close/state |
| `screenshot` / `shot` | **yes** | capture |
| `launch` / `open` | **yes** | start process / shell-open |
| `browser_*` | **yes** | Playwright Spaces / CDP browser |
| `clipboard_set` / `clipboard_image_save` | **yes** | write clipboard / save image |
| `proc` list | no | inventory |
| `proc` kill | **yes** | needs confirm=true |
| `desktop` | list no / switch yes | pyvda optional |
| `notify` | no | agent signal (stub via env/step) |
| `wait` / `wait_until` / `wait_gone` / `wait_change` / `verify` | no | timing / UI asserts |



## 1.7 safety ops

| op | lease? | purpose |
|----|--------|---------|
| `verify` / `verify_ui` | no | Fail-closed UI assert (`ok:false` when expect absent) |
| `wait_change` | no | Screen change **or** expect-text wait (fail-closed if text absent) |
| `kill_switch` / `arm_kill_switch` / `disarm_kill_switch` | no | Arm/disarm; mutating exec steps return `ok:false` with `kill_switch` error, zero injects |
| `action_log` / `log` / `recent_actions` | no | Last N mutating injects (timestamp + outcome) |
| `lease_force_release` | no | Cross-process sticky-lease cleanup (token/agent/unconditional) |
| `lease_release` | no | Accepts `token` / `lease` on a **fresh** engine (no in-process acquire required) |

**Rate limits** — `max_actions_per_minute` / `max_clicks_per_minute` from config; under burst mutating ops block with explicit `rate limit: …` reason (not silent drop).

**Destructive confirm** — patterns `delete all`, `shutdown`, `rm -rf`, `format` (see `safety.require_confirm_patterns`) hard-block type/fill/keys/hotkey/open/launch text unless `confirm=true`.

## Multi-agent etiquette

1. Acquire lease with a clear `task` string.
2. Focus → act → verify in one `aether_exec` script when possible.
3. Renew on long jobs; always release when done (or let TTL expire).
4. Never fight an active holder — wait or coordinate out-of-band.

## 1.8.0 Jarvis+ ops

- `notify` — real Windows toast (BurntToast → WinRT → NotifyIcon). Use `stub: true` or `AETHER_NOTIFY_STUB=1` only in tests.
- `clipboard_image_set` / `clipboard_set_image` — `{op, path}` puts a PNG/JPEG onto the clipboard (lease required).
- `browser_click` / `browser_wait` — accept `text` / `name` / `query` (snapshot resolve, then click/wait). Example: `{op: browser_click, text: Settings}`.
- `wait_window` — `{op, title?, pid?, timeout?}` polls until the window appears (lease-free).

