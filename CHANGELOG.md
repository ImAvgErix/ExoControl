# Changelog

Version history for the **Exo Control** Python package.  
This is a library (pip / wheel), not a Setup.exe. GitHub Release may include the wheel + sdist.

## 2.0.0

- **Physical package invert:** implementation lives in `src/exo_control/`. `src/aether/` is a thin compat shim (`import aether` still works).
- CLI entry points call `exo_control.cli:main`.
- `python -m exo_control` and `python -m exo_control.slim_mcp_server` are the real MCP.
- Honest safety (lease token hidden, allowroots not escaped by confirm, env redaction, loopback CDP, live Notepad test).
- Dropped Riot/Epic/BFS probe examples and internal capability-checklist docs.
- PyPI pending trusted publisher registered for `exo-control`.

## 1.3.0

Breaking honesty (safety claims now match the code):

- **Lease token never leaves `lease_status`.** Same-agent `lease_acquire` renews. `force_release` needs token, holder `agent_id`, an expired lease, or `EXO_ALLOW_FORCE_RELEASE=1`.
- **`confirm=true` no longer unlocks the filesystem.** Outside `EXO_FILE_ROOTS` stays denied unless the operator sets `EXO_ALLOW_OUTSIDE_ROOTS=1`.
- **`env_get` redacts secret-like names** unless `EXO_ALLOW_ENV_VALUES=1`.
- **Kill fail-closed** if the PID cannot be named. No `taskkill /T`. Expanded anti-cheat list. Critical services denied.
- **CDP attach is loopback-only.** Discovery drops websocket debugger URLs. `browser_eval` needs `confirm=true` (`EXO_DENY_BROWSER_EVAL=1` hard-denies).
- **`screenshot_on_fail` default off.** MCP `exo_screenshot` requires a lease. Compact strips `image_base64` / `fail_screenshot`.
- **One MCP door.** `aether.mcp_server` is a deprecation shim. `aether_*` tools register only when `EXO_MCP_ALIASES=1`.
- **CLI click/focus/read/shot** go through `ExoExecEngine` (auto-lease).
- **Lazy import.** `import exo_control` / `exo-control doctor` / `exo_help` no longer construct the desktop stack. Playwright is extra `[browser]`.
- **Launch focuses the new window** so the next `type`/`click` does not fail with act-without-focus.
- **Catalog is the lease source of truth.** Compact `help` (14 core ops); `capabilities` / `detail=true` for the rest.
- **Password redaction** on UIA ValuePattern and DOM `input[type=password]`.
- Public package surface: `ExoExecEngine`, `ExoConfig`, compact helpers. `SmartController` stays internal/compat.

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
