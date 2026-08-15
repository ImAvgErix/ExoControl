# Exo Control — agent instructions (any model, any harness)

You have **eyes and hands on a Windows PC** via Exo Control. You are not limited to one vendor UI.

## How you call it

1. **MCP tools** (preferred if available): `exo_exec`, `exo_screenshot`, `exo_help`
2. **CLI**: `exo-control exec --steps '...'` or `exo-control script file.json`
3. **Python**: `ExoExecEngine().execute([...])` (alias: `AetherExecEngine`)

If you do not know an op, run `{"op":"help"}` or `exo_help` first.

## Non-negotiable workflow

1. **Lease** before hands: `lease_acquire` with your `agent_id` + short `task`
2. **Plan a script** — batch many steps in one `exo_exec` call
3. **Focus** the window (`title` substring; optional `monitor`)
4. **Observe/read** structure — do **not** screenshot first
5. **Act** (click/type/fill/scroll/browser_*) then **verify**
6. **lease_release** when done

You are a person at the desk. Aim the pointer. Roll the wheel on the document. Glance after you move.

## Do / don't

| Do | Don't |
|----|--------|
| UIA / DOM / refs | Coordinate spam |
| `scroll` / `scroll_into_view` / `browser_scroll` | Home / End (they jump the caret, they are not scroll) |
| Read `seen` after hands (live eyes) | Assume the screen did not change |
| `require_change` when UI should flip | Assume click worked |
| `confirm=true` for kill/registry write/delete | Silent destructive OS ops or `confirm` to escape allowroots |
| Fail closed and report step errors | Invent window titles or UI text |
| Compact observe | Dump full trees / raw HTML |

## Safety hard stops

No anti-cheat kill, no unnamed-PID kill, no silent elevation. `lease_status` does not include the token. Files stay in `EXO_FILE_ROOTS`. See SECURITY.md.

## Exo Launcher (optional target)

Installed at `%LOCALAPPDATA%\ExoLauncher\app\ExoLauncher.exe`. Prefer CDP/DOM when CDP is up; UIA otherwise. Not required for Control to be useful — Notepad, browsers, and any Win app work too.

## Example

```json
[
  {"op": "lease_acquire", "agent_id": "agent", "task": "open notepad", "ttl_sec": 120},
  {"op": "launch", "app": "notepad"},
  {"op": "type", "text": "ready"},
  {"op": "lease_release"}
]
```

Web facts (lease-free): `{"op":"search","query":["…","…"]}` with `PERPLEXITY_API_KEY`. That is not UI find — use `type`/`click` for in-app search boxes. Full page markdown: `{"op":"scrape","url":"…"}` (`FIRECRAWL_API_KEY`).

Cloud web agent: `{"op":"browser_use","task":"…"}` with `BROWSER_USE_API_KEY`. Cloud Chromium: `browser_use_start` then `browser_connect` (`provider=browser-use` or the returned `cdp_url`). Local page UI stays `browser_*`. Stagehand `browser_act` / AgentQL `browser_query` / Skyvern `skyvern` are lease-free HTTP, not CDP hands.

Docs on disk: `files_convert` / `files_find`. Facts: `memory_add` / `memory_search`. Screen history: `recall`. Mail/calendar: `mail_list` / `cal_next` (Graph or Composio).

Exo Control is **Windows-only**. ego lite has no Windows app — do not call `ego-browser`. `{"op":"ego"}` reports that.

Full catalog: [docs/HARNESS.md](docs/HARNESS.md) · capability bar: [docs/CAPABILITY.md](docs/CAPABILITY.md)
