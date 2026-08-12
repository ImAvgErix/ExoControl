# Jarvis OS — Full-PC realtime bar

**Jarvis OS CLEARED 2026-08-11** by Product (Floor + all P0 [x]). P1 may trail.


Grade pass/fail only. **Jarvis** and **Jarvis-Plus P0** are the floor, not the ceiling.
North star: elite realtime computer use across desktop, browser, files, registry, and OS infrastructure — at elite token efficiency.
Source: Product via General (Eric). Stamp name: **Jarvis OS**.

## Floor (must already hold)
- [x] Jarvis 19/19 still green
- [x] Jarvis-Plus P0 all [x] on disk, including multi-window orchestration + DOM loop with honest clear/back (or line amended to match proved scope)
- Plus P1 may trail; does not block Jarvis OS start, but OS stamp still requires Floor [x]

## P0 — Token & efficiency (first-class)

- [x] **Compact-by-default eyes:** default `observe`/`compact_observe`/`eyes`/`browser_snapshot` responses stay under a hard cap (≤4KB chars or ≤40 refs) unless `verbose=true`; raw HTML/a11y full trees never dump by default
  - **CODE** + **PROVE**: same Exo screen twice — default payload ≤ cap; verbose exceeds only when asked
- [x] **No screenshot-default:** structure/DOM path succeeds without `aether_screenshot` for Exo Settings→Library and one desktop Notepad type; screenshot only on explicit ask or structure miss
  - **PROVE**
- [x] **Batched exec:** a 6+ step workflow runs in **one** `aether_exec` (one MCP round-trip); mid-script state (lease, CDP, focus) sticks
  - **PROVE**
- [x] **Ref-stable acts:** click/type/fill accept compact refs from the prior observe/snapshot in the same script (no re-sending prose descriptions)
  - **CODE** + **PROVE**
- [x] **Budget gate:** Exo compact_observe p95 < 300ms and p95 payload < cap over 50 warm calls
  - **PROVE** (+ **CODE** if over)

## P0 — Desktop / UIA hands

- [x] UIA-first click/type/fill/scroll on WinUI + classic Win32; coords only after UIA miss (logged)
  - **PROVE**
- [x] Multi-window leased script: ≥3 apps, correct HWND each act, no cross-talk
  - **PROVE** (Plus residual if still open — close it here)
- [x] Cursor workers STA-safe; dual-cursor UIA acts both succeed
  - **PROVE**

## P0 — Browser (DOM/CDP, not pixels-first)

- [x] Chrome/Edge CDP + Exo WebView2: navigate, snapshot (refs), click/type by ref/text, zero screenshots in the happy path
  - **PROVE**
- [x] Exo DOM loop: Settings → Library → search → clear/back in one exec, zero UIA/OCR
  - **PROVE** (honesty vs Plus note)
- [x] Structure miss → one bounded retry → then optional screenshot; never screenshot-first
  - **CODE** + **PROVE**

## P0 — Files

- [x] `files_list` / read text / write text / copy / move / delete under an allowrooted agent workspace; paths outside roots require `confirm=true`
  - **CODE** + **PROVE**
- [x] Open file via shell (`open_path`) and verify window or honest fail
  - **PROVE**
- [x] No recursive wipe / `rm -rf` equivalent without confirm; deny leaves audit line
  - **CODE** + **PROVE**

## P0 — Registry

- [x] Read HKCU (and explicitly allowed HKLM read) values by path; missing key → ok:false (no throw dump)
  - **CODE** + **PROVE**
- [x] Write HKCU only with `confirm=true`; HKLM write denied or confirm+elevated policy documented
  - **CODE** + **PROVE**
- [x] Results compact: name/type/value only — no whole-tree dumps by default
  - **CODE** + **PROVE**

## P0 — OS infrastructure

- [x] Process inventory compact (pid/name/exe); kill requires `confirm=true` + lease; protected/anti-cheat names hard-deny
  - **CODE** + **PROVE**
- [x] Service list + status; start/stop/restart require `confirm=true`; failure returns Win32 reason compactly
  - **CODE** + **PROVE**
- [x] Deeper system control stays behind explicit ops (env read, scheduled task list, startup folder list) — mutating ones need confirm; no silent persistence
  - **CODE** + **PROVE**
- [x] Crash honesty: target app kill mid-script fails ≤15s, lease recoverable, no zombie MCP session
  - **PROVE**

## P1 — Elite presence

- [x] Multi-monitor observe/focus/shot bind (`monitor` on focus/observe/screenshot; wrong-monitor fail closed)
- [x] Persistent UI memory across relaunch with invalidate-on-miss (`~/.aether/state/ui_memory.json`, process-name keys)
- [x] Clipboard image round-trip + real notify toast (BurntToast → WinRT → NotifyIcon; env stub ignored)
- [x] Fuzzy launch → wait_window for installed apps (PATH + alias + Start Menu `.lnk` fuzzy; default `wait_ready` for app names)

## Hard stops (never for Jarvis OS)
- Anti-cheat / kernel tampering / credential dumping / silent elevation
- Default-on screenshots, raw HTML dumps, unbounded observe trees
- Registry or service mutation without confirm
- Claiming “full OS control” while files/registry/services are stubs

## Won't stamp Jarvis OS if
Token path is screenshot-first or verbose-by-default; browser work is pixels-first; files/registry/services missing or unboundedly destructive; Plus floor boxes still open on disk.

## Assignment hint
1. Close Plus P0 residuals on disk (multi-window tick + DOM clear/back honesty)
2. CODE: compact caps, ref-stable acts, files allowroot, registry ops, service ops, confirm gates
3. PROVE: efficiency budgets, DOM-first browser, batched multi-surface script, registry/service happy+deny paths
4. Product clears **Jarvis OS** only when Floor + all P0 [x]

## 1.9.0 CODE landed (2026-08-11)

P0 CODE surface is on disk (PROVE boxes still open until live budgets/DOM runs):

- `aether.compact.compact_payload` — default eyes/snapshot ≤4KB / ≤40 refs; `verbose=true` opt-out
- Exec wraps `observe` / `compact_observe` / `eyes` / `browser_snapshot` (+ fat `read_ui`); stores `_last_browser_refs`; structure-miss click retries once via fresh snapshot (no screenshot unless `screenshot_on_miss`)
- `observe_budget` — lease-free p50/p95 ms + p95 chars over N warm compact_observe calls
- `files_list|read|write|copy|move|delete` — allowrooted (`%USERPROFILE%\.aether\workspace` + `AETHER_FILE_ROOTS`); outside/recursive need `confirm=true` + audit jsonl
- `registry_read` / `registry_write` — HKCU write confirm; HKLM write always denied
- `proc_list` / protected kill deny; `service_list|status|control`; `env_get|list`; `tasks_list`; `startup_list`

