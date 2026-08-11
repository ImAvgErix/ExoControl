# API stability (v0.1)

## Stable for v0.1

- Python: `import aether` and `aether.*` submodules (compat)
- Python: `import exo_control` and `exo_control.*` (preferred; re-exports `aether`)
- CLI: `exo-control` and `aether` entry points (both call the same CLI)
- MCP tool ops: unchanged op names (`browser_connect`, `files_list`, …)

## Rename window

- Preferred new import: `import exo_control` / `from exo_control.exec_engine import AetherExecEngine`
- Package name on PyPI/GitHub: `exo-control` / ExoControl
- Internal module folder remains `src/aether/` until a breaking v0.2+ physical rename
- Submodule aliases are registered for common modules (`exec_engine`, `browser`, `compact`, `files_ops`, `registry_ops`, `infra_ops`, …)

Do not break `aether.*` imports in v0.1 patches.
