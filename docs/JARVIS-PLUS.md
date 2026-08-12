# Jarvis-Plus — next bar (floor was 19/19)

Grade pass/fail only. Jarvis stamped ≠ done. This is live-in-the-PC beyond the floor.
**Jarvis-Plus CLEARED 2026-08-11** by Product (all P0 [x]). Ceiling is now `docs/JARVIS-OS.md`.
Source: Product via General. Track STA marshal from Jarvis follow-up here too.

## P0 — must feel native (ship next)

### STA / cursor inject (carry-forward)
- [x] UIA/click/type from `cursor_exec` worker completes without hang; injects marshal to STA/main pump
  - **CODE** then **PROVE**: dual-cursor script clicks a named Exo control via each cursor; both succeed <5s

### Exo DOM-native loop
- [x] One `aether_exec` drives Exo purely via CDP/DOM: Settings → Library → search type → clear/back, zero UIA/OCR clicks
  - **PROVED 2026-08-11**: sticky-loop-v1 one execute — Settings click+wait Launcher settings, Home library (incl. Back to library synonym), search fill fields{"Search to install":"celeste"} then clear to "", snapshot Home library. Zero UIA. Re-prove after dirty CDP (extra create_space pages) showed Settings click timeout — keep Exo page count clean for DOM scripts.
  - **PROVE** (CODE only if browser_* gaps): script returns ok each hop; `browser_snapshot` shows expected chrome text after each step

### Multi-window orchestration
- [x] Single leased script orchestrates Exo + browser Space + Notepad: focus/act/verify each without stealing wrong HWND
  - **PROVED 2026-08-11**: same lease — Exo CDP fill/search value, browser Space navigate https://example.com (explicit space_id), Notepad type verified via clipboard (UIA verify on Edit weak); focus Exo <-> Notepad. create_space does not switch default space_id.
  - **PROVE** (+ thin **CODE** if focus ranking gaps): final verify sees expected title/text in all three; lease held throughout

### Exo transition waits
- [x] `wait_change` / `wait_gone` on Exo UI transitions fail closed and succeed when real (e.g. open Settings chrome appears; leave and target gone)
  - **PROVE** first; **CODE** if flaky >1/10 on Debug Exo

### Crash / recovery honesty
- [x] Kill Exo mid-script → step fails with honest error (no hang ≥15s); lease releasable/reacquire; relaunch CDP Exo → `wait_cdp` + discover live again
  - **CODE** (timeouts/cleanup) + **PROVE**

### Fuzzy launch → ready
- [x] `launch` by fuzzy app name (`notepad`, `chrome`) resolves install/path, starts process, waits until window title ready (or explicit fail)
  - **CODE** + **PROVE**: notepad ready ≤10s; unknown name → ok:false with reason

## P1 — presence & speed

### Multi-monitor
- [x] `observe`/`focus`/`screenshot` accept monitor id; shot/observe bind to that monitor’s HWND/region; wrong-monitor capture = fail
  - **CODE** + **PROVE 2026-08-12**: dual 1920×1080 layout; focus/observe on mon2 ok; observe mon1 with focus on mon2 → fail closed; unit tests + live smoke

### Persistent UI memory
- [x] After process relaunch, memory re-finds a previously successful control by process name (survives PID recycle); miss invalidates entry
  - **CODE** (`ui_memory.json` under `AETHER_STATE_DIR`, invalidate-on-miss) + **PROVE**: unit persist/reload + smart_click invalidates memory-sourced misses

### Observe latency
- [x] `compact_observe` on focused surface p95 < 300ms over warm calls (warm lease, no screenshot)
  - **PROVE 2026-08-12**: live compact_observe ~6–160ms without OCR screenshot path; suite budget gate still available via `observe_budget`

### Clipboard image + notify
- [x] Clipboard image get/set round-trip (known PNG hash); `notify` shows a visible Windows toast the agent can correlate by title/body
  - **CODE** + **PROVE 2026-08-12**: live `_notify_toast` → method `winrt` ok

## P2 — cut / defer

### Voice / listen
- **CUT** for Plus. Not required to live in the PC; realtime listen stays experimental until eyes/hands/multi-window are boring-reliable. Reopen only with a falsifiable wake→act→verify loop and privacy bar.

## Won't call Plus yet if
DOM Exo loop still needs UIA, multi-window scripts mis-focus, mid-script Exo death hangs the agent, fuzzy launch is path-only, or cursor UIA still STA-deadlocks.

## Assignment hint
1. CODE: STA marshal, fuzzy launch ready, crash timeouts, notify real, multi-monitor bind, memory persist
2. PROVE: Exo DOM loop, multi-window script, wait_change/gone on Exo, observe p95, clipboard image
3. Product clears **Jarvis-Plus** only when all P0 [x]; P1 can trail as 1.8.x
