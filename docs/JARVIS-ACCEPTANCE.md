# Jarvis-level Aether — acceptance checklist

Grade pass/fail only. Source: Product via General. Aether must clear this before we call it live-in-the-PC.

## Eyes
- [x] `observe`/`read` on a focused WinUI/desktop window returns named controls (name/role/bounds) for ≥5 visible actionable targets without a screenshot
- [x] `aether_screenshot` matches the focused window title and is ≤1600 max-side; wrong-window capture = fail
- [x] `verify` / `wait_change` fails closed when expected text is absent (no false pass)

## Hands
- [x] Click path prefers UIA invoke over coords for a named button; same click twice does not double-fire mid-action (cursor queue serializes)
- [x] `type`/`fill`/`keys` deliver exact unicode/hotkey into the focused field; clipboard get/set round-trips a known string
- [x] `focus` by title OR pid brings the target foreground before act; act-without-focus = fail

## Apps/files
- [x] `launch` starts a known exe with optional cwd/env; process visible in `windows`/`status` within 10s
- [x] `open`/`open_path`/`open_url` opens a local file and a https URL via shell without agent-owned download
- [x] Destructive patterns (`delete all`, `shutdown`, `rm -rf`, `format`) are blocked or require explicit confirm gate before inject

## Multi-agent safety
- [x] Two cursors (`worker-1`, `worker-2`) can run parallel queues; one cursor's steps never interleave mid-action with the other's
- [x] Kill switch armed → next `aether_exec` step returns blocked, zero injects; disarm restores
- [x] Rate limits trip under burst (actions/clicks per minute) with explicit block reason, not silent drop
- [x] Single shared desktop lock or documented exclusive mode: two agents cannot both claim foreground exclusive on the same HWND without one waiting/failing

## Exo / WebView2
- [x] With Exo launched CDP-enabled (`EXO_CDP` / Launch-ExoWithCdp), `cdp_discover` returns a live endpoint + ≥1 page target for Exo's WebView2
- [x] Browser/DOM ops against that CDP can `browser_snapshot` Exo UI text without pixel OCR
- [x] Without CDP, discover returns empty/honest miss — never invents an Exo DOM session

## Reliability
- [x] Multi-step `aether_exec` with `stop_on_failure=true` halts on first fail and reports which step; session still usable next script
- [x] Action log records each inject with timestamp + outcome; last N steps inspectable
- [x] Cold start: slim MCP up → `status` ok → observe+click+verify on a known app within 30s, three times in a row

## Won't call Jarvis yet if
Eyes need screenshots for every decision, hands only work via blind coords, Exo is pixels-only with no CDP path, or two agents can fight the same foreground without a hard gate.
