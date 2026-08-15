# Exo Control — capability bar

**Cleared 2026-08-11** (Floor + all P0). P1 presence items closed 2026-08-12.

Grade pass/fail only. North star: elite realtime computer use across desktop, browser, files, registry, and OS infrastructure — at elite token efficiency.

Product: **Exo Control** · Repo: [ImAvgErix/ExoControl](https://github.com/ImAvgErix/ExoControl) · Family: Exo Launcher / Exo Control

## Floor

- [x] Live Notepad loop in `tests/test_live_notepad.py` (lease → launch → type → verify → close)
- [x] Compact observe, leased hands, confirm gates, anti-cheat deny

## P0 — Token & efficiency (first-class)

- [x] **Compact-by-default eyes:** default `observe`/`compact_observe`/`eyes`/`browser_snapshot` responses stay under a hard cap (≤4KB chars or ≤40 refs) unless `verbose=true`; raw HTML/a11y full trees never dump by default
- [x] **No screenshot-default:** structure/DOM path succeeds without screenshot for Exo Settings→Library and one desktop Notepad type; screenshot only on explicit ask or structure miss
- [x] **Batched exec:** a 6+ step workflow runs in **one** `exo_exec` (one MCP round-trip); mid-script state (lease, CDP, focus) sticks
- [x] **Ref-stable acts:** click/type/fill accept compact refs from the prior observe/snapshot in the same script
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
- [x] Write HKCU only with `confirm=true`; HKLM write denied
- [x] Results compact: name/type/value only

## P0 — OS infrastructure

- [x] Process inventory compact; kill requires `confirm=true` + lease; protected/anti-cheat names hard-deny
- [x] Service list + status; start/stop/restart require `confirm=true`
- [x] env / scheduled tasks / startup list behind explicit ops; mutating ones need confirm
- [x] Crash honesty: target app kill mid-script fails ≤15s, lease recoverable

## P1 — Presence

- [x] Multi-monitor observe/focus/shot bind (`monitor`; wrong-monitor fail closed)
- [x] Persistent UI memory across relaunch with invalidate-on-miss
- [x] Clipboard image round-trip + real Windows notify toast
- [x] Fuzzy launch → wait_window (PATH + alias + Start Menu)
- [x] Perplexity Search as Code: lease-free `search` / `search_content` (HTTP; Windows-safe)
- [x] Browser Use Cloud: `browser_use` hosted run + `browser_use_start` Chromium (Windows-reachable HTTP/CDP)
- [x] ego lite: honest Windows-only miss (`ego`); local stand-in is `browser_*` spaces
- [x] Firecrawl: lease-free `scrape` / `crawl` / `site_map` (HTTP; Windows-safe)
- [x] MarkItDown: allowrooted `files_convert` / `read_doc` (local; txt/json/csv/html builtin)
- [x] Stagehand: lease-free `stagehand` / `browser_act` / `stagehand_extract` (HTTP)
- [x] Skyvern: lease-free `skyvern` vision task (HTTP)
- [x] OmniParser: `omni` screenshot → elements (`OMNIPARSER_URL` or fail closed)
- [x] AgentQL: lease-free `agentql` / `browser_query` (HTTP)
- [x] Everything: `files_find` (HTTP, else walk allowroots)
- [x] Memory: `memory_add` / `memory_search` (local JSONL; Mem0 if keyed)
- [x] Composio / Graph: `composio`, `mail_list`, `cal_next`, `drive_get`
- [x] Screenpipe: `recall` / `screen_search` (localhost history)
- [x] Graph Wave 1: `todo` / `onenote` / `teams` / `mail_send` / `xlsx` (CSV or workbook)
- [x] Jina `read_url`; allowrooted `git`; GitHub `gh_pr`
- [x] Windows desk: `volume` / `winget` / `recycle` / `eventlog` / `ocr_win` / `stt` / `tts`
- [x] `window_move` (lease); `browser_network` / `browser_downloads` / `browser_pdf` / `browser_tabs`

## Hard stops

- Anti-cheat / kernel tampering / credential dumping / silent elevation
- Default-on screenshots, raw HTML dumps, unbounded observe trees
- Registry or service mutation without confirm
- Claiming “full OS control” while files/registry/services are stubs

## Install (library — no installer EXE)

```bash
pip install -e .
# or PYTHONPATH to src
python -m exo_control.slim_mcp_server
```

See [HARNESS.md](HARNESS.md) and root [README.md](../README.md).
