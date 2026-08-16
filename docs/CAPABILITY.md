# Exo Control — capability bar

**Cleared 2026-08-11** (Floor + all P0). P1 presence items closed 2026-08-12.

Grade pass/fail only. North star: elite realtime computer use across desktop, browser, files, registry, and OS infrastructure — at elite token efficiency.

Product: **Exo Control** · Repo: [ImAvgErix/ExoControl](https://github.com/ImAvgErix/ExoControl) · Family: Exo Launcher / Exo Control

## Floor

- [x] Live Notepad loop in `tests/test_live_notepad.py` (lease → launch → type → verify → close)
- [x] Compact observe, leased hands, confirm gates, anti-cheat deny

## P0 — Token & efficiency (first-class)

- [x] Default observe is fused eyes (a11y + OpenCV grounding + OCR when available), bound to the focused window
- [x] **Compact-by-default eyes:** default `observe`/`compact_observe`/`eyes`/`browser_snapshot` responses stay under a hard cap (≤4KB chars or ≤40 refs) unless `verbose=true`; raw HTML/a11y full trees never dump by default
- [x] **No screenshot-default:** structure/DOM path succeeds without screenshot for Exo Settings→Library and one desktop Notepad type; screenshot only on explicit ask or structure miss
- [x] **Batched exec:** a 6+ step workflow runs in **one** `exo_exec` (one MCP round-trip); mid-script state (lease, CDP, focus) sticks
- [x] **Ref-stable acts:** click/type/fill accept compact refs from the prior observe/snapshot; session hits survive the next exec until session_close
- [x] **Budget gate:** Exo `compact_observe` p95 < 300ms and p95 payload < cap over warm calls

## P0 — Desktop / UIA hands

- [x] UIA-first click/type/fill/scroll on WinUI + classic Win32; coords only after UIA miss (logged)
- [x] Multi-window leased script: ≥3 apps, correct HWND each act, no cross-talk
- [x] Cursor workers STA-safe; dual-cursor UIA acts both succeed

## P0 — Browser (DOM/CDP, not pixels-first)

- [x] Chrome/Edge CDP + Exo WebView2: navigate, snapshot (refs), click/type by ref/text, zero screenshots in the happy path
- [x] Exo DOM loop: Settings → Library → search → clear/back in one exec, zero UIA/OCR
- [x] Structure miss → one bounded retry → then optional screenshot; never screenshot-first

## P0 — Files

- [x] `files_list` / read / write / copy / move / delete under an allowrooted agent workspace; paths outside roots stay denied unless the operator sets `EXO_ALLOW_OUTSIDE_ROOTS=1` *and* `confirm=true`
- [x] Open file via shell (`open_path`) and verify window or honest fail
- [x] No recursive wipe without confirm; deny leaves audit line

## P0 — Registry

- [x] Read HKCU (and allowed HKLM read) by path; missing key → ok:false
- [x] Write HKCU only with `confirm=true`; HKLM write denied in default/trusted; Full-Trust + broker writes HKLM
- [x] Results compact: name/type/value only

## P0 — OS infrastructure

- [x] Process inventory compact; kill requires `confirm=true` + lease; protected/anti-cheat names hard-deny in default/trusted
- [x] Service list + status; start/stop/restart require `confirm=true`
- [x] env / scheduled tasks / startup list behind explicit ops; mutating ones need confirm
- [x] Crash honesty: target app kill mid-script fails ≤15s, lease recoverable

## P1 — Presence

- [x] Multi-monitor observe/focus/shot bind (`monitor`; wrong-monitor fail closed)
- [x] Persistent UI memory across relaunch with invalidate-on-miss
- [x] Clipboard image round-trip + real Windows notify toast
- [x] Fuzzy launch → wait_window (PATH + alias + Start Menu)
- [x] Search as Code: lease-free `search` (`provider=perplexity|tavily|exa|ddg|serper|brave`) + `search_content`
- [x] Browser Use Cloud: `browser_use` hosted run + `browser_use_start` Chromium (Windows-reachable HTTP/CDP)
- [x] ego lite: honest Windows-only miss (`ego`); local stand-in is `browser_*` spaces
- [x] Firecrawl / Jina: lease-free `scrape` (`provider=firecrawl|jina`); `crawl` / `site_map`
- [x] MarkItDown / Docling: allowrooted `files_convert` (`engine=markitdown|docling`; txt/json/csv/html builtin)
- [x] Stagehand: lease-free `stagehand` / `browser_act` / `stagehand_extract` (HTTP)
- [x] Skyvern: lease-free `skyvern` vision task (HTTP)
- [x] OmniParser: `omni` screenshot → elements (`OMNIPARSER_URL` or fail closed)
- [x] AgentQL: lease-free `agentql` / `browser_query` (HTTP)
- [x] Everything: `files_find` (HTTP, else walk allowroots)
- [x] Memory: `memory_add` / `memory_search` (local JSONL; Mem0 if keyed)
- [x] Composio / Graph: `composio`, `mail_list`, `cal_next`, `drive_get`
- [x] Screenpipe: `recall` / `screen_search` (localhost history)
- [x] Graph Wave 1: `todo` / `onenote` / `teams` / `mail_send` / `xlsx` (CSV or workbook)
- [x] Jina via `scrape` `provider=jina`; allowrooted `git`; GitHub `gh_pr`
- [x] Windows desk: `volume` / `winget` / `recycle` / `eventlog` / `tts`
- [x] Default `observe` is fused eyes (a11y + window-local OpenCV + OCR when available); session hit cache survives the next exec; `ocr_win` is Windows.Media.Ocr (not a stub). `stt` stays a stub
- [x] `window_move` (lease); `browser_network` / `browser_downloads` / `browser_pdf` / `browser_tabs`
- [x] Wave 2: `rag` / `winsearch` / `steel_start` / `search` providers / `slack` / `notion` / `linear`
- [x] Wave 2 shells/sys: `pwsh` / `wsl` / `docker` / `print` / `wifi` / `power` / `disk` / `whoami` / `certs` / `hash` / `lnk` / `dialog`
- [x] Waves 3–5: Graph writes, CDP extras, open-data search, more SaaS, zip/sqlite/tree, sys status (no secret dump / UAC / anti-cheat)
- [x] Pilot (original): `goal` / `checkpoint` / `proof` / `changed` / `undo` / `skill_save` / `skill_run` / `heal`
- [x] Stock Windows natives (ctypes/netsh/PowerShell/COM) for volume, lock, wifi, power, recycle, TTS, dialog, dark_mode, idle, ports, Defender status, …
- [x] Honest `ready` map: what works here vs Windows-native vs needs a key (`stt` stays stub; `ocr_win` is WinRT)
- [x] Live seat: `session_open` holds the desk like remote access; `pointer` / `mouse` / `keypress` / `drive` are raw HID (not UIA, not RDP)

## P2 — Full-PC computer use (2.2)

- [x] Trust levels: default / trusted / Full-Trust (env + first-time ack + audit). Kill file `~/.exo/KILL` always wins
- [x] Full-Trust owner mode: no Exo policy denials; elevated broker for HKLM / Program Files / services (MCP stays medium IL). Kill file still wins.
- [x] `web_task` — multi-step browser job in one leased exec (structure/ref path). Optional extra `[web]` (Browser Use) when an LLM key is present
- [x] Browser extras: `browser_back` / `forward` / `tabs` / `extract` / `select`
- [x] Window move / resize / snap; files mkdir/stat/exists/search; `os_info` / `drives` / `which` / `proc_info`
- [x] Persistent session: remember/recall, plan, checkpoint, recover last focus

## P3 — The rest of the PC (2.4)

- [x] `find` returns refs from last read/observe (or a fresh read)
- [x] `pc` snapshot: audio / power / idle / network / wifi / recycle / clock
- [x] Volume + mute (default render device). Brightness honest on desktop. Lock / sleep (confirm)
- [x] WLAN profiles + connect (confirm). `ms-settings:` open. Wallpaper get/set. Recycle count/empty
- [x] winget search/list/install (install confirm). File hash/zip/unzip/touch/reveal
- [x] `watch_file` / `watch_proc`. Right-click and double-click do not go through UIA invoke
- [x] `menu`, `copy` / `paste` / `select_all`. Script cap 128 steps

## Hard stops

- Default/trusted: anti-cheat / unnamed PID / HKLM / System32 / critical services
- Default-on screenshots, raw HTML dumps, unbounded observe trees
- Registry or service mutation without confirm (unless Full-Trust)
- Activating Full-Trust from env alone (ack file required) or from ack alone (env required)
- Agent or broker disarming `~/.exo/KILL`
- Elevating the MCP process itself (UIPI)

## Install (library — no installer EXE)

```bash
pip install exo-control
# fallback: pip install -e .  or  pip install "git+https://github.com/ImAvgErix/ExoControl.git@v2.2.0"
python -m exo_control.slim_mcp_server
```

See [HARNESS.md](HARNESS.md) and root [README.md](../README.md).
