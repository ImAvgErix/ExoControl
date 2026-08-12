# Changelog

## 1.0.1 — 2026-08-12

**Any AI · any harness** — Control is a control plane, not a single-vendor plugin.

- **Self-describe:** exec ops `help` / `ops` / `capabilities` + MCP `exo_help` / `aether_help`
- **Dual MCP tools:** `exo_exec` / `exo_screenshot` / `exo_help` with full `aether_*` aliases
- **MCP accepts** list, JSON string, or `{"steps":[...]}` (host-shape tolerant)
- **CLI:** `exo-control ops|help|exec|mcp|monitors` — JSON in/out for shell-tool agents
- **Docs:** `docs/HARNESS.md`, root `AGENTS.md`, `skills/exo-control/SKILL.md`
- Grok skill updated to harness-agnostic wording
- Tests: `tests/test_harness_agnostic.py`

## 1.0.0 — 2026-08-12


Jarvis OS **complete** release: Floor + P0 + P1 on disk and unit/live smoke proved.

### Elite presence (P1)

- **Multi-monitor bind** — `monitor` on `focus` / `observe` / `screenshot` / `list_windows`. Wrong-monitor focus or capture fails closed with monitor inventory.
- **Persistent UI memory** — `UIMemory` writes `%USERPROFILE%\.aether\state\ui_memory.json`; keys prefer process name over PID; **invalidate-on-miss** after memory-sourced click failures.
- **Fuzzy launch → ready** — PATH + alias table + Start Menu `.lnk` fuzzy scan; common apps (Discord, Steam, Spotify, Chrome, Edge, Code, Exo). App-name launches **default `wait_ready`** until a matching window appears.
- **Notify** — real Windows toast (BurntToast → WinRT → NotifyIcon). `AETHER_NOTIFY_STUB` cannot fake done; only step `stub:true` stubs.
- **Realtime eyes** — honor focus monitor hint for capture region.

### Efficiency / honesty

- Compact observe remains default; screenshots are not the happy path.
- `compact_observe` with `monitor` binds OCR to that display without poisoning when `read_ui` adopts the foreground.

### Docs & packaging

- README aligned with Exo Launcher (badges, clear install, MCP, safety).
- Jarvis OS / Plus P1 boxes ticked with prove notes.
- Version **1.0.0** (`pyproject.toml`, `aether.__version__`).

### Tests

- `tests/test_monitors_memory_launch.py` — monitor filter/bind, memory persist/invalidate, Start Menu resolve, launch wait_ready.
- Full suite: 109+ passed.

## 0.1.0 — 2026-08-11

Announce-GA / Jarvis OS P0: compact eyes, files/registry/infra, CDP page-pick, dual `exo_control` package, lease safety.
