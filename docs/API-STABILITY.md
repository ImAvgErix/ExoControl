# API stability (v1.0)

## Stable for v1.0

- Python: `import aether` and `aether.*` submodules (compat)
- Python: `import exo_control` and `exo_control.*` (preferred; re-exports `aether`)
- CLI: `exo-control` and `aether` entry points (both call the same CLI)
- MCP tool ops: existing op names remain; additive fields only

### Additive in 1.0 (non-breaking)

- `monitor` on `focus` / `smart_focus` / `observe` / `compact_observe` / `screenshot` / `list_windows`
- Launch: Start Menu fuzzy resolve; default `wait_ready` for `app`/`name`/`query` (set `wait_ready:false` to skip)
- Persistent UI memory path + process-name keys (behavior upgrade; no op rename)

## Rename window

- Preferred new import: `import exo_control` / `from exo_control.exec_engine import AetherExecEngine`
- Package name on GitHub: `exo-control` / ExoControl
- Internal module folder remains `src/aether/` until a future major physical rename
- Submodule aliases are registered for common modules (`exec_engine`, `browser`, `compact`, `files_ops`, `registry_ops`, `infra_ops`, …)

Do not break `aether.*` imports in 1.x patches.
