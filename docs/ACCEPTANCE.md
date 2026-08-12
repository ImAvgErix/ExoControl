# Exo Control — acceptance checklist

Grade pass/fail only. Clear this before calling Exo Control live-in-the-PC.

## Eyes

- [x] `observe`/`read` on a focused WinUI/desktop window returns named controls (name/role/bounds) for ≥5 visible actionable targets without a screenshot
- [x] Screenshot matches the focused window title and is ≤1600 max-side; wrong-window capture = fail
- [x] `verify` / `wait_change` fails closed when expected text is absent (no false pass)

## Hands

- [x] Click path prefers UIA invoke over coords for a named button; same click twice does not double-fire mid-action
- [x] `type`/`fill`/`keys` deliver exact unicode/hotkey into the focused field; clipboard get/set round-trips a known string
- [x] `focus` by title OR pid brings the target foreground before act; act-without-focus = fail

## Apps / files

- [x] `launch` starts a known exe with optional cwd/env; process visible in `windows`/`status` within 10s
- [x] `open`/`open_path`/`open_url` opens a local file and a https URL via shell
- [x] Destructive patterns (`delete all`, `shutdown`, `rm -rf`, `format`) are blocked or require explicit confirm

## Multi-agent safety

- [x] Two cursors can run parallel queues; steps never interleave mid-action across cursors
- [x] Kill switch armed → next exec step returns blocked, zero injects; disarm restores
- [x] Rate limits trip under burst with explicit block reason
- [x] Single shared desktop lock: two agents cannot both claim exclusive hands without one waiting/failing

## Exo Launcher / WebView2

- [x] With Exo launched CDP-enabled, `cdp_discover` returns a live endpoint + ≥1 page target
- [x] Browser/DOM ops can `browser_snapshot` Exo UI text without pixel OCR
- [x] Without CDP, discover returns empty/honest miss — never invents a session

## Reliability

- [x] Multi-step exec with `stop_on_failure=true` halts on first fail and reports which step
- [x] Action log records each inject with timestamp + outcome
- [x] Cold start: slim MCP up → `status` ok → observe+click+verify on a known app within 30s

## Won't ship as ready if

Eyes need screenshots for every decision, hands only work via blind coords, Exo is pixels-only with no CDP path, or two agents can fight the same foreground without a hard gate.
