# Changelog

Version history for the **Exo Control** Python package.  
There is **no installer EXE** and no GitHub Release assets — install via `pip install -e .` or set `PYTHONPATH`.

## 1.2.0

- **Stable refs:** `read`/`observe` stamp `eN` refs; `click`/`type` accept `ref`
- **Screenshot-on-fail:** failed steps attach compact `fail_screenshot` (disable with `screenshot_on_fail:false`)
- **finally/cleanup:** script object `{steps, finally}` always runs cleanup steps
- **last_error:** op returns most recent failed step evidence
- **wait_all / wait_any:** composed conditions (also `wait` with `all`/`any`)
- **Type paste fallback:** Ctrl+V path when synthetic type is not visible
- **CI:** `scripts/accept_cdp_chromium.py` launches Chromium with CDP (required green)

## 1.1.0

- **Document text:** `read`/`observe` include values via UIA Value/Text + Win32 edit; clipboard is last resort with `via` flag
- **Result envelope:** every exec result is `{ok, ...}`; `windows` always `{ok, windows, count}`
- **STA warnings:** pywinauto STA COM warning silenced (debug log once)
- **Rename surface:** preferred `ExoExecEngine`, state under `~/.exo/` (legacy `.aether` migrated/read)
- **CDP accept:** `scripts/accept_cdp_live.py` + `Prove-Acceptance.ps1` (skip-ok without debugger)
- **Install:** one-liner `pip install "git+https://github.com/ImAvgErix/ExoControl.git"`; CI + publish workflows
- User-facing strings say Exo Control (not Aether)

## 1.0.2

- **Honesty:** type/verify use document content (UIA Value/Text + select-all/copy), not pixel-diff alone
- **window_close:** default `discard_unsaved=true` clicks **Don't Save** (never Save); invalidates window list cache
- **Eyes:** `read`/`observe` expose `values` / `a11y_values`; compact_observe sets `ok`
- **Cold start:** easyocr/torch lazy-loaded only when OCR is requested
- **proc_kill:** accept `name` or `pid`; protected names hard-deny without requiring a pid
- **Exec envelope:** every step has top-level `ok`; auto `lease_release` on early-stop failure
- **CLI:** `exo-control doctor` detects dual-install shadowing
- **Docs:** MCP config no longer points at `~\.aether\aether-driver` PYTHONPATH
- Status capabilities honest per platform (`ax_mac` only on Darwin)

## 1.0.1

- Harness-agnostic surface: `help` / `ops` / `capabilities`, dual `exo_*` + `aether_*` MCP tools
- CLI: `exo-control ops|help|exec|mcp|monitors`
- Docs: `docs/HARNESS.md`, root `AGENTS.md`, `skills/exo-control/SKILL.md`

## 1.0.0

- Multi-monitor bind, persistent UI memory, fuzzy Start Menu launch, real Windows notify
- Capability bar P0 + P1 closed (see `docs/CAPABILITY.md`)

## 0.1.0

- Announce path: compact eyes, files/registry/infra, CDP, dual `exo_control` / `aether` packages, lease safety
