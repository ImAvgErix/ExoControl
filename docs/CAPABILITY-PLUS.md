# Exo Control — Plus bar

Beyond the acceptance floor. Live-in-the-PC reliability for multi-app and native feel.

**Plus P0 CLEARED 2026-08-11.** Ceiling continues in [CAPABILITY.md](CAPABILITY.md).

## P0 — must feel native

### STA / cursor inject
- [x] UIA/click/type from `cursor_exec` worker completes without hang; injects marshal to STA/main pump

### Exo DOM-native loop
- [x] One `exo_exec` drives Exo purely via CDP/DOM: Settings → Library → search → clear/back, zero UIA/OCR clicks

### Multi-window orchestration
- [x] Single leased script orchestrates Exo + browser Space + Notepad without stealing wrong HWND

### Exo transition waits
- [x] `wait_change` / `wait_gone` on Exo UI transitions fail closed and succeed when real

### Crash / recovery honesty
- [x] Kill Exo mid-script → step fails with honest error (no hang ≥15s); lease recoverable; relaunch CDP Exo works

### Fuzzy launch → ready
- [x] `launch` by fuzzy app name resolves install/path, starts process, waits until window ready (or explicit fail)

## P1 — presence & speed

### Multi-monitor
- [x] `observe` / `focus` / `screenshot` accept monitor id; wrong-monitor capture = fail

### Persistent UI memory
- [x] Memory re-finds successful controls after process relaunch (process-name keys); miss invalidates

### Observe latency
- [x] `compact_observe` warm path under budget (see `observe_budget`)

### Clipboard image + notify
- [x] Clipboard image get/set; real Windows toast (`notify`)

## P2 — cut / defer

### Voice / listen
- **CUT** for Plus. Not required to live in the PC until eyes/hands/multi-window are boring-reliable.

## Won't call Plus yet if
DOM Exo loop still needs UIA, multi-window scripts mis-focus, mid-script death hangs the agent, fuzzy launch is path-only, or cursor UIA still STA-deadlocks.
