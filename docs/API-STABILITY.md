# API stability (v0.1)

## Stable for v0.1

- Python: `import aether` and `aether.*` submodules
- CLI: `exo-control` and `aether` entry points (both call the same CLI)
- MCP tool ops: unchanged op names (`browser_connect`, `files_list`, …)

## Rename window

- Preferred new import: `import exo_control` (re-exports `aether` in v0.1)
- Package name on PyPI/GitHub: `exo-control` / ExoControl
- Internal module folder remains `src/aether/` until a breaking v0.2+ rename

Do not break `aether.*` imports in v0.1 patches.
