# Changelog

Version history for the **Exo Control** Python package.  
This is a library (pip / wheel), not a Setup.exe. GitHub Release may include the wheel + sdist.

## 2.5.0

Fused eyes by default.

- **Default observe** runs window-local OpenCV grounding + OCR (when an in-process backend exists) + a11y. Missing OCR is honest (`ocr: "unavailable"`, `ocr_count=0`).
- **Session hits.** Observe stores fused `{ref,label,kind,bbox,source,visible}` on the session. The next exec can `click` those refs. New observe replaces the cache; `session_close` clears it.
- **click** matches session hits first (ref/label/kind), then UIA. Coords are last-resort and unverified 0.55 guesses are `ok:false`.
- **`ocr_win`** is Windows.Media.Ocr via WinRT (in-process `winrt`/`winsdk` or in-box PowerShell). Fail closed (`ok:false`, `UNAVAILABLE`) if the engine is missing. Fused observe prefers winocr, then tesseract, then lazy easyocr.
- **Glance** after click/type: cheap `seen` (title + whether the claimed label/hit still matches). No JPEG.

## 2.4.0

The rest of the PC. Eyes that find. Hands that right-click for real.

- **`find`.** Search the last `read`/`observe` (or a fresh read) for a query and get refs back. In the compact catalog.
- **Owner snapshot.** `pc` / `exo-control pc` — audio, power, idle, network, wifi, recycle, clock in one compact payload.
- **Audio / display / power.** Get/set default playback volume and mute (Core Audio). Laptop brightness via WMI (honest fail on desktop). AC/battery + plan. `lock`. `sleep` (confirm). `idle` ms since last input.
- **Network.** Adapter list. WLAN profile + current SSID. `wifi_connect` to a saved profile (confirm).
- **Settings / wallpaper / bin.** `settings_open` (`ms-settings:` or aliases). Wallpaper get/set (set needs confirm + allowroot file). Recycle count; `recycle_empty` (confirm).
- **Packages.** `package` / `winget` search + list; install needs confirm.
- **Files extras.** `files_hash` (SHA-256), `files_zip` / `files_unzip` (zip-slip safe), `files_touch`, `files_reveal`.
- **Watch.** `watch_file` exists/gone/changed. `watch_proc` running/gone.
- **Hands.** `right_click` and `double_click` use SendInput/coords — UIA invoke is left-click only. `menu` = right-click then item. `copy` / `paste` / `select_all`.
- **Scripts.** Max steps 128 (was 64).

## 2.3.0

Owner mode. Full-Trust is unrestricted Exo policy plus a persistent elevated broker.

- **Full-Trust lifts every Exo hard-deny** (HKLM / HKCR / HKU, Program Files / Windows writes, anti-cheat kill, unnamed PID, critical services, wipe patterns, non-loopback CDP). Default and trusted stay as they were.
- **Elevated broker.** MCP stays medium IL (UIPI — clicks keep working). Privileged ops retry through a loopback helper running as admin. First use may show **one** UAC; after that the `ExoControl\\ElevatedBroker` logon task starts it without a prompt.
- **CLI / ops.** `exo-control elevate status|install|start`; steps `elevate_status`, `elevate_install`, `registry_delete`, `run_elevated`.
- **Still sacred.** `~/.exo/KILL` / `EXO_KILL_SWITCH=1` cannot be disarmed by the agent or the broker. Set `EXO_DISABLE_ELEVATE=1` to skip the broker (tests).
- **Trust levels / session / web (local 2.2 work).** `default` / `trusted` / `full`. `web_task`. Browser back/forward/tabs/extract/select. `window_move` / `resize` / `snap`. `files_mkdir` / `stat` / `exists` / `search`. `os_info` / `drives` / `which` / `proc_info`. `remember` / `recall` / `plan` / `recover`.


- **Trust levels.** `default` (safe) / `trusted` / `full`. Full-Trust requires `EXO_TRUST=full` (or `EXO_FULL_TRUST=1`) **and** `exo-control trust enable --ack "I own this PC"`. Audit log under `~/.exo/state/trust_audit.jsonl`.
- **Full-Trust behavior.** Most confirms optional; user-profile file roots; longer lease TTL with auto-renew on hands. Hard denies kept: anti-cheat, unnamed PID, critical services, HKLM, Windows/Program Files writes, non-loopback CDP, wipe/shutdown patterns.
- **Human kill-switch.** `~/.exo/KILL` or `exo-control trust kill` / `EXO_KILL_SWITCH=1`. Agents cannot disarm a kill file.
- **`web_task`.** Multi-step browser job in one leased exec (structure/ref path). Optional extra `[web]` integrates Browser Use when an LLM key is set.
- **Browser.** `browser_back` / `forward` / `tabs` / `extract` / `select`.
- **Windows / files / OS.** `window_move` / `resize` / `snap`; `files_mkdir` / `stat` / `exists` / `search`; `os_info` / `drives` / `which` / `proc_info`.
- **Session.** `remember` / `recall` / `plan` / `checkpoint` / `recover` persist under `~/.exo/state/sessions/`.

## 2.2.0

Live seat, Pilot, stock Windows natives, and the desk-ops catalog.

- **Live seat.** `session_open` / `seat` takes the desk like remote access (lease + eyes) and holds it across `execute()` calls until `session_close`. `session_status` never returns the token. `pointer` / `mouse` / `keypress` / `drive` are raw SendInput HID (not UIA, not RDP).
- **Pilot.** `goal` / `checkpoint` / `proof` / `changed` / `undo` / `skill_save` / `skill_run` / `heal`. When a goal is set, successful hands re-glance and attach `changed`.
- **`ready`.** Honest map: works here / Windows-native / needs a key. `stt` stays a stub.
- **Stock Windows natives** (ctypes / netsh / PowerShell / COM, no extra pip): volume, recycle, TTS, wifi, power, print, dialog, lnk, certs, winsearch walk, lock, idle, brightness, dark_mode, ports, uptime, USB, Bluetooth, printers, BitLocker status, Defender status, hotfixes, fonts.
- **`search` / `search_web`.** Fan-out queries (`provider=perplexity|tavily|exa|ddg|serper|brave`). Not UI find. Auth for Perplexity is `PERPLEXITY_API_KEY`; missing key fails closed.
- **`search_content` / `search_snippets`.** Query-relevant snippets scoped to `urls`.
- **Browser Use Cloud.** `browser_use`, `browser_use_start` / `browser_use_stop`. `browser_connect` accepts `provider=browser-use` when `BROWSER_USE_API_KEY` is set.
- **ego lite.** Status-only. Exo Control is Windows-only; local page UI stays `browser_*`.
- **Merged families.** `search` `provider=`, `files_convert` `engine=markitdown|docling`, `scrape` `provider=firecrawl|jina`, `files_stat` with PDF/image extras. Old names stay as aliases.
- **Addon + Waves 1–5.** Firecrawl, Stagehand, Skyvern, OmniParser, AgentQL, Everything, memory, Graph, Screenpipe, git, `gh_pr`, Steel, Slack/Notion/Linear/Jira/Discord, pwsh/wsl/docker, zip/sqlite/tree, open data, and Windows desk/sys ops. Writes, exec, lock, and cookie values need `confirm=true`. No LSASS / UAC / anti-cheat / captcha / secret-dump ops.

## 2.1.0

Human substitute — sit in the chair, use the mouse wheel, look at the screen.

- **Aimed SendInput wheel.** `scroll` moves the pointer into the document (below chrome) and sends `MOUSEEVENTF_WHEEL` one notch at a time. Positive notches = page down. Never Home/End.
- **`scroll_into_view`** wheels until a query/bbox sits in the focused viewport.
- **`hover`** eases the pointer (no teleport) so hover menus work.
- **Browser page scroll.** `browser_scroll` uses `window.scrollBy` on the document; `browser_scroll_into_view` / `browser_hover` are first-class.
- **Live eyes.** `lease_acquire` starts the realtime loop. After hands, results include a compact `seen` glance (`title`, `changed`, labels). `eyes_read` / `look` / `glance`. Off with `EXO_LIVE_EYES=0` or `seen:false`.
- Core catalog now includes `scroll`, `scroll_into_view`, `hover`.

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
