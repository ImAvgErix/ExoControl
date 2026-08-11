# Exo Control — charter

## Positioning

Harness-agnostic realtime PC control: desktop/UIA, browser DOM/CDP, files, registry, OS infrastructure. Any AI agent via MCP (Cursor, Claude Desktop, …), CLI (ether / xo-control), or Python SDK.

**Pitch:** realtime PC eyes and hands for any AI agent. Compact. Leased. Honest.

## Name & slug

- **GitHub:** [ImAvgErix/ExoControl](https://github.com/ImAvgErix/ExoControl)
- **PyPI / CLI:** xo-control (CLI alias ether during rename)

## Relationship

| Repo | Role |
|------|------|
| [ExoLauncher](https://github.com/ImAvgErix/ExoLauncher) | Launcher app |
| **Exo Control** (this repo) | Eyes/hands stack for Exo and any Windows app |

Exo is a first-class target, not required. Control must work without Exo.

## Promise

Structure-first, compact-by-default. Screenshot only on ask or structure miss. Batched exec over chatty single acts. Agents lease the desktop; they do not own it.

## Capability bar

[docs/JARVIS-OS.md](JARVIS-OS.md) — Product clears **Jarvis OS** when Floor + all P0 are [x]. That doc is the bar; this charter does not restate the checklist.

## Non-goals

- Anti-cheat / kernel tampering
- Credential dumping
- Silent elevation
- Harness lock-in (Cursor-only, Claude-only, etc.)
- Building ExoLauncher UI in this repo
- Voice/listen as a launch blocker

## License

MIT. Public repo. Alpha until Jarvis OS stamp (see SECURITY.md).
