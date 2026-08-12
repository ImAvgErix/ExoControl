# API stability (v1.1)

## Stable for v1.x

- Python: `import exo_control` / `from exo_control import ExoExecEngine` (**preferred**)
- Python: `import aether` and `aether.*` (**compat** through 1.x)
- Python: `AetherExecEngine` is an alias of `ExoExecEngine`
- CLI: `exo-control` (preferred); `aether` entry point still works
- MCP tools: `exo_*` preferred; `aether_*` aliases remain
- MCP op names: existing ops remain; additive fields only

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

Internal module folder remains `src/aether/` until a future major.  
Do not break `aether.*` imports in 1.x patches.
