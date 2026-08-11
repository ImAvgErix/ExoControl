# Jarvis OS — Full-PC realtime bar

Grade pass/fail only. **Jarvis** and **Jarvis-Plus P0** are the floor, not the ceiling.
North star: elite realtime computer use across desktop, browser, files, registry, and OS infrastructure — at elite token efficiency.
Source: Product via General (Eric). Stamp name: **Jarvis OS**.

## Floor (must already hold)
- [x] Jarvis 19/19 still green
- [x] Jarvis-Plus P0 all [x] on disk, including multi-window orchestration + DOM loop with honest clear/back (or line amended to match proved scope)
- Plus P1 may trail; does not block Jarvis OS start, but OS stamp still requires Floor [x]

## P0 — Token & efficiency (first-class)

- [ ] **Compact-by-default eyes:** default `observe`/`compact_observe`/`eyes`/`browser_snapshot` responses stay under a hard cap (≤4KB chars or ≤40 refs) unless `verbose=true`; raw HTML/a11y full trees never dump by default
  - **CODE** + **PROVE**: same Exo screen twice — default payload ≤ cap; verbose exceeds only when asked
- [ ] **No screenshot-default:** structure/DOM path succeeds without `aether_screenshot` for Exo Settings→Library and one desktop Notepad type; screenshot only on explicit ask or structure miss
  - **PROVE**
- [ ] **Batched exec:** a 6+ step workflow runs in **one** `aether_exec` (one MCP round-trip); mid-script state (lease, CDP, focus) sticks
  - **PROVE**
- [ ] **Ref-stable acts:** click/type/fill accept compact refs from the prior observe/snapshot in the same script (no re-sending prose descriptions)
  - **CODE** + **PROVE**
- [ ] **Budget gate:** Exo compact_observe p95 < 300ms and p95 payload < cap over 50 warm calls
  - **PROVE** (+ **CODE** if over)

## P0 — Desktop / UIA hands

- [ ] UIA-first click/type/fill/scroll on WinUI + classic Win32; coords only after UIA miss (logged)
  - **PROVE**
- [ ] Multi-window leased script: ≥3 apps, correct HWND each act, no cross-talk
  - **PROVE** (Plus residual if still open — close it here)
- [ ] Cursor workers STA-safe; dual-cursor UIA acts both succeed
  - **PROVE**

## P0 — Browser (DOM/CDP, not pixels-first)

- [ ] Chrome/Edge CDP + Exo WebView2: navigate, snapshot (refs), click/type by ref/text, zero screenshots in the happy path
  - **PROVE**
- [ ] Exo DOM loop: Settings → Library → search → clear/back in one exec, zero UIA/OCR
  - **PROVE** (honesty vs Plus note)
- [ ] Structure miss → one bounded retry → then optional screenshot; never screenshot-first
  - **CODE** + **PROVE**

## P0 — Files

- [ ] `files_list` / read text / write text / copy / move / delete under an allowrooted agent workspace; paths outside roots require `confirm=true`
  - **CODE** + **PROVE**
- [ ] Open file via shell (`open_path`) and verify window or honest fail
  - **PROVE**
- [ ] No recursive wipe / `rm -rf` equivalent without confirm; deny leaves audit line
  - **CODE** + **PROVE**

## P0 — Registry

- [ ] Read HKCU (and explicitly allowed HKLM read) values by path; missing key → ok:false (no throw dump)
  - **CODE** + **PROVE**
- [ ] Write HKCU only with `confirm=true`; HKLM write denied or confirm+elevated policy documented
  - **CODE** + **PROVE**
- [ ] Results compact: name/type/value only — no whole-tree dumps by default
  - **CODE** + **PROVE**

## P0 — OS infrastructure

- [ ] Process inventory compact (pid/name/exe); kill requires `confirm=true` + lease; protected/anti-cheat names hard-deny
  - **CODE** + **PROVE**
- [ ] Service list + status; start/stop/restart require `confirm=true`; failure returns Win32 reason compactly
  - **CODE** + **PROVE**
- [ ] Deeper system control stays behind explicit ops (env read, scheduled task list, startup folder list) — mutating ones need confirm; no silent persistence
  - **CODE** + **PROVE**
- [ ] Crash honesty: target app kill mid-script fails ≤15s, lease recoverable, no zombie MCP session
  - **PROVE**

## P1 — Elite presence (trails OK)

- [ ] Multi-monitor observe/focus/shot bind
- [ ] Persistent UI memory across relaunch with invalidate-on-miss
- [ ] Clipboard image round-trip + real notify toast (not stub)
- [ ] Fuzzy launch → wait_window for top N installed apps via Apps folder / PATH

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
