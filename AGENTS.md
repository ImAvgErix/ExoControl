# Exo Control — agent instructions (any model, any harness)

You have **eyes and hands on a Windows PC** via Exo Control. You are not limited to one vendor UI.

## How you call it

1. **MCP tools** (preferred if available): `exo_exec`, `exo_screenshot`, `exo_help`  
   (aliases: `aether_exec`, `aether_screenshot`, `aether_help`)
2. **CLI**: `exo-control exec --steps '...'` or `exo-control script file.json`
3. **Python**: `ExoExecEngine().execute([...])` (alias: `AetherExecEngine`)

If you do not know an op, run `{"op":"help"}` or `exo_help` first.

## Non-negotiable workflow

1. **Lease** before hands: `lease_acquire` with your `agent_id` + short `task`
2. **Plan a script** — batch many steps in one `exo_exec` call
3. **Focus** the window (`title` substring; optional `monitor`)
4. **Observe/read** structure — do **not** screenshot first
5. **Act** (click/type/fill/browser_*) then **verify**
6. **lease_release** when done

## Do / don't

| Do | Don't |
|----|--------|
| UIA / DOM / refs | Coordinate spam |
| `require_change` when UI should flip | Assume click worked |
| `confirm=true` for kill/registry write/delete | Silent destructive OS ops |
| Fail closed and report step errors | Invent window titles or UI text |
| Compact observe | Dump full trees / raw HTML |

## Safety hard stops

No anti-cheat kill, no credential dumping, no silent elevation. See SECURITY.md.

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

Full catalog: [docs/HARNESS.md](docs/HARNESS.md) · capability bar: [docs/CAPABILITY.md](docs/CAPABILITY.md)
