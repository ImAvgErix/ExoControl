"""Harness-agnostic op catalog — any AI can self-describe the surface.

Used by exec ops ``help`` / ``ops`` / ``capabilities``, MCP instructions, and CLI.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


# Compact catalog: op aliases → lease, purpose, common fields.
# Keep this the source of truth for agent discovery (not prose-only docs).
OPS: List[Dict[str, Any]] = [
    # Discovery / lease-free
    {"op": "help", "aliases": ["ops", "capabilities", "catalog"], "lease": False,
     "purpose": "List ops and harness rules for any AI", "fields": ["detail?", "query?"]},
    {"op": "status", "aliases": [], "lease": False, "purpose": "Driver health / capabilities", "fields": []},
    {"op": "stats", "aliases": [], "lease": False, "purpose": "Latency / reliability counters", "fields": ["reset?"]},
    {"op": "windows", "aliases": ["list_windows"], "lease": False,
     "purpose": "Top-level windows", "fields": ["monitor?"]},
    {"op": "monitors", "aliases": ["list_monitors"], "lease": False,
     "purpose": "Physical displays (id/left/top/width/height)", "fields": []},
    {"op": "observe", "aliases": ["compact_observe"], "lease": False,
     "purpose": "Compact a11y (+ optional OCR); token-capped", "fields": ["include_ocr?", "monitor?", "verbose?"]},
    {"op": "read", "aliases": ["read_ui"], "lease": False,
     "purpose": "Focused/target UIA tree (compact)", "fields": ["interactive?", "max_elements?"]},
    {"op": "eyes", "aliases": [], "lease": False,
     "purpose": "compact_observe + CDP endpoint summary", "fields": ["include_ocr?"]},
    {"op": "apps", "aliases": [], "lease": False, "purpose": "Running apps pid/title/exe", "fields": ["max?"]},
    {"op": "cdp", "aliases": ["cdp_discover", "exo_cdp"], "lease": False,
     "purpose": "Discover DevTools endpoints (Chrome/Edge/Exo WebView2)", "fields": ["port?"]},
    {"op": "wait_cdp", "aliases": ["wait_for_cdp"], "lease": False,
     "purpose": "Poll until CDP is up", "fields": ["timeout?", "port?", "poll?"]},
    {"op": "clipboard_get", "aliases": [], "lease": False, "purpose": "Read clipboard text", "fields": []},
    {"op": "notify", "aliases": [], "lease": False,
     "purpose": "Windows toast (real; stub only if step stub:true)", "fields": ["title", "body"]},
    {"op": "wait", "aliases": ["wait_until"], "lease": False,
     "purpose": "Wait for text/control; or all=/any= condition lists", "fields": ["text?", "query?", "all?", "any?", "timeout?", "poll?"]},
    {"op": "wait_all", "aliases": [], "lease": False,
     "purpose": "Wait until every condition succeeds", "fields": ["all|conditions", "timeout?"]},
    {"op": "wait_any", "aliases": [], "lease": False,
     "purpose": "Wait until any condition succeeds", "fields": ["any|conditions", "timeout?"]},
    {"op": "wait_gone", "aliases": [], "lease": False, "purpose": "Wait until control gone", "fields": ["query", "timeout?"]},
    {"op": "wait_change", "aliases": [], "lease": False,
     "purpose": "Wait for UI change or expect text", "fields": ["expect?", "timeout?"]},
    {"op": "wait_window", "aliases": [], "lease": False,
     "purpose": "Poll until window title/pid appears", "fields": ["title?", "pid?", "timeout?"]},
    {"op": "verify", "aliases": ["verify_ui"], "lease": False,
     "purpose": "Fail-closed UI assert", "fields": ["expect?", "expect_gone?", "timeout?"]},
    {"op": "last_error", "aliases": ["error", "last_fail"], "lease": False,
     "purpose": "Most recent failed step evidence (this engine)", "fields": []},
    {"op": "lease_acquire", "aliases": [], "lease": False,
     "purpose": "Hold desktop hands (required for mutating ops)", "fields": ["agent_id", "task?", "ttl_sec?"]},
    {"op": "lease_renew", "aliases": [], "lease": False, "purpose": "Extend lease", "fields": ["token?", "ttl_sec?"]},
    {"op": "lease_release", "aliases": [], "lease": False, "purpose": "Release desktop lease", "fields": ["token?"]},
    {"op": "lease_status", "aliases": [], "lease": False, "purpose": "Who holds the lease", "fields": []},
    {"op": "lease_force_release", "aliases": [], "lease": False,
     "purpose": "Clear sticky lease (token/agent/unconditional)", "fields": ["token?", "agent_id?"]},
    {"op": "files_list", "aliases": [], "lease": False,
     "purpose": "List dir under allowroot", "fields": ["path", "max?", "confirm?"]},
    {"op": "files_read", "aliases": [], "lease": False, "purpose": "Read text file under allowroot", "fields": ["path"]},
    {"op": "registry_read", "aliases": [], "lease": False, "purpose": "Read registry value", "fields": ["path", "name?"]},
    {"op": "proc_list", "aliases": [], "lease": False, "purpose": "Process inventory", "fields": ["max?"]},
    {"op": "service_list", "aliases": [], "lease": False, "purpose": "Windows services", "fields": []},
    {"op": "service_status", "aliases": [], "lease": False, "purpose": "One service status", "fields": ["name"]},
    {"op": "env_get", "aliases": [], "lease": False, "purpose": "Env var", "fields": ["name"]},
    {"op": "env_list", "aliases": [], "lease": False, "purpose": "Env vars (compact)", "fields": ["prefix?"]},
    {"op": "tasks_list", "aliases": [], "lease": False, "purpose": "Scheduled tasks (compact)", "fields": ["max?"]},
    {"op": "startup_list", "aliases": [], "lease": False, "purpose": "Startup folder entries", "fields": ["max?"]},
    {"op": "observe_budget", "aliases": [], "lease": False,
     "purpose": "Warm compact_observe p50/p95 ms + chars", "fields": ["n?"]},
    {"op": "kill_switch", "aliases": ["arm_kill_switch", "disarm_kill_switch"], "lease": False,
     "purpose": "Arm/disarm global kill (blocks hands)", "fields": ["armed?"]},
    {"op": "action_log", "aliases": ["log", "recent_actions"], "lease": False,
     "purpose": "Recent mutating injects", "fields": ["n?"]},
    # Hands (lease required)
    {"op": "focus", "aliases": ["smart_focus"], "lease": True,
     "purpose": "Foreground window by title/pid; optional monitor bind", "fields": ["title?", "pid?", "monitor?"]},
    {"op": "click", "aliases": ["smart_click"], "lease": True,
     "purpose": "UIA-first click by query, ref (eN from read/observe), or x,y",
     "fields": ["query?", "ref?", "x?", "y?", "require_change?", "screenshot_on_fail?"]},
    {"op": "type", "aliases": ["smart_type"], "lease": True,
     "purpose": "Type text (optional focus query/ref); paste fallback if needed",
     "fields": ["text", "query?", "ref?", "clear?", "confirm?"]},
    {"op": "fill", "aliases": [], "lease": True, "purpose": "Fill field by query", "fields": ["query", "text", "confirm?"]},
    {"op": "scroll", "aliases": ["smart_scroll"], "lease": True, "purpose": "Scroll", "fields": ["dy?", "dx?", "query?"]},
    {"op": "drag", "aliases": ["smart_drag"], "lease": True, "purpose": "Drag", "fields": ["x1", "y1", "x2", "y2"]},
    {"op": "hotkey", "aliases": ["smart_hotkey", "keys", "press"], "lease": True,
     "purpose": "Hotkey chord", "fields": ["keys"]},
    {"op": "screenshot", "aliases": ["shot"], "lease": True,
     "purpose": "JPEG/path capture; monitor/title bind fail-closed", "fields": ["title?", "monitor?", "path?", "max_side?"]},
    {"op": "launch", "aliases": ["start", "run"], "lease": True,
     "purpose": "Fuzzy app launch + wait_ready default for app names",
     "fields": ["app?", "name?", "command?", "wait_ready?", "title?", "timeout?", "args?"]},
    {"op": "open", "aliases": ["open_path", "open_url"], "lease": True,
     "purpose": "Shell-open path/url", "fields": ["path?", "url?", "target?"]},
    {"op": "window_min", "aliases": ["window_minimize"], "lease": True, "purpose": "Minimize", "fields": ["title?", "hwnd?"]},
    {"op": "window_max", "aliases": ["window_maximize"], "lease": True, "purpose": "Maximize", "fields": ["title?", "hwnd?"]},
    {"op": "window_restore", "aliases": [], "lease": True, "purpose": "Restore", "fields": ["title?", "hwnd?"]},
    {"op": "window_close", "aliases": [], "lease": True,
     "purpose": "Close window (default: Don't save on unsaved prompts)", "fields": ["title?", "hwnd?", "discard_unsaved?"]},
    {"op": "clipboard_set", "aliases": [], "lease": True, "purpose": "Set clipboard text", "fields": ["text"]},
    {"op": "clipboard_image_set", "aliases": ["clipboard_set_image"], "lease": True,
     "purpose": "Put image file on clipboard", "fields": ["path"]},
    {"op": "clipboard_image_save", "aliases": [], "lease": False,
     "purpose": "Save clipboard image to path", "fields": ["path"]},
    {"op": "files_write", "aliases": [], "lease": True,
     "purpose": "Write text under allowroot", "fields": ["path", "text", "confirm?"]},
    {"op": "files_copy", "aliases": [], "lease": True, "purpose": "Copy file", "fields": ["path", "dest", "confirm?"]},
    {"op": "files_move", "aliases": [], "lease": True, "purpose": "Move file", "fields": ["path", "dest", "confirm?"]},
    {"op": "files_delete", "aliases": [], "lease": True,
     "purpose": "Delete file (confirm for recursive/outside roots)", "fields": ["path", "confirm?"]},
    {"op": "registry_write", "aliases": [], "lease": True,
     "purpose": "Write HKCU (confirm); HKLM write denied", "fields": ["path", "name", "value", "confirm"]},
    {"op": "proc_kill", "aliases": [], "lease": True,
     "purpose": "Kill process (confirm; anti-cheat hard-deny by name or pid)", "fields": ["pid?", "name?", "confirm"]},
    {"op": "service_control", "aliases": [], "lease": True,
     "purpose": "start/stop/restart service", "fields": ["name", "action", "confirm"]},
    {"op": "desktop", "aliases": [], "lease": "switch", "purpose": "Virtual desktop list/switch", "fields": ["action?"]},
    # Browser
    {"op": "browser_connect", "aliases": [], "lease": True, "purpose": "Connect CDP browser", "fields": ["cdp_url?", "port?"]},
    {"op": "browser_spaces", "aliases": [], "lease": True, "purpose": "List browser spaces", "fields": []},
    {"op": "browser_create_space", "aliases": [], "lease": True, "purpose": "New space", "fields": []},
    {"op": "browser_navigate", "aliases": [], "lease": True, "purpose": "Navigate", "fields": ["url", "space_id?"]},
    {"op": "browser_snapshot", "aliases": [], "lease": True,
     "purpose": "DOM snapshot with refs (compact)", "fields": ["space_id?", "include_screenshot?", "verbose?"]},
    {"op": "browser_click", "aliases": [], "lease": True,
     "purpose": "Click by ref/text/selector", "fields": ["ref?", "text?", "name?", "query?", "selector?", "space_id?"]},
    {"op": "browser_type", "aliases": [], "lease": True, "purpose": "Type in browser", "fields": ["text", "ref?", "space_id?"]},
    {"op": "browser_press", "aliases": [], "lease": True, "purpose": "Key in browser", "fields": ["key", "space_id?"]},
    {"op": "browser_scroll", "aliases": [], "lease": True, "purpose": "Scroll page", "fields": ["dy?", "space_id?"]},
    {"op": "browser_wait", "aliases": [], "lease": True,
     "purpose": "Wait for text/name", "fields": ["text?", "name?", "timeout?", "space_id?"]},
    {"op": "browser_fill", "aliases": [], "lease": True, "purpose": "Fill form fields", "fields": ["fields", "space_id?"]},
    {"op": "browser_eval", "aliases": [], "lease": True, "purpose": "Evaluate JS", "fields": ["js", "space_id?"]},
    {"op": "browser_close_space", "aliases": [], "lease": True, "purpose": "Close space", "fields": ["space_id"]},
]

HARNESS_RULES: List[str] = [
    "Works with ANY AI via MCP (stdio), CLI, or Python — not tied to one vendor.",
    "Script-first: prefer one batched exec with many steps over chatty single clicks.",
    "Acquire lease_acquire before hands (click/type/launch/browser/files write).",
    "Eyes first: observe/read/windows/verify; screenshots only when structure is insufficient.",
    "Compact by default; set verbose=true only when you need full trees.",
    "Focus by title; WinUI host ranks above WebView2 child windows.",
    "monitor=N binds focus/observe/shot to that display; wrong-monitor fails closed.",
    "Mutating OS ops need confirm=true; anti-cheat / silent elevation hard-deny.",
    "Always lease_release when done (or let TTL expire).",
    "Never invent UI state — use step results / observe / verify.",
]

MINIMAL_SCRIPT_EXAMPLE: List[Dict[str, Any]] = [
    {"op": "lease_acquire", "agent_id": "any-agent", "task": "demo", "ttl_sec": 120},
    {"op": "launch", "app": "notepad"},
    {"op": "focus", "title": "Notepad"},
    {"op": "type", "text": "hello from exo-control"},
    {"op": "notify", "title": "Exo Control", "body": "Done"},
    {"op": "lease_release"},
]


def list_ops(*, query: Optional[str] = None, detail: bool = False) -> Dict[str, Any]:
    q = (query or "").strip().lower()
    rows = []
    for entry in OPS:
        names = [entry["op"], *entry.get("aliases", [])]
        if q and not any(q in n for n in names) and q not in (entry.get("purpose") or "").lower():
            continue
        row = {
            "op": entry["op"],
            "aliases": list(entry.get("aliases") or []),
            "lease": entry.get("lease"),
            "purpose": entry.get("purpose"),
        }
        if detail:
            row["fields"] = list(entry.get("fields") or [])
        rows.append(row)
    return {
        "ok": True,
        "count": len(rows),
        "ops": rows,
        "rules": list(HARNESS_RULES),
        "example": list(MINIMAL_SCRIPT_EXAMPLE),
        "surfaces": {
            "mcp": "python -m exo_control.slim_mcp_server",
            "mcp_compat": "python -m aether.slim_mcp_server",
            "cli": "exo-control script steps.json",
            "cli_exec": "exo-control exec  (JSON array on stdin or --steps)",
            "python": "from exo_control import ExoExecEngine",
        },
        "tools": {
            "mcp": ["exo_exec", "exo_screenshot", "exo_help", "aether_exec", "aether_screenshot", "aether_help"],
            "note": "exo_* and aether_* are aliases — same engine.",
        },
    }


def mcp_instructions() -> str:
    return (
        "Exo Control — realtime Windows eyes/hands for ANY AI harness (MCP/CLI/Python). "
        "Use exo_exec (alias aether_exec) with a JSON array of steps. "
        "Always start mutating work with {\"op\":\"lease_acquire\",\"agent_id\":\"…\",\"task\":\"…\"} "
        "and end with lease_release. Prefer structure: focus → observe/read → click/type → verify. "
        "Screenshots only when pixels matter (exo_screenshot / aether_screenshot). "
        "Call exo_help or step {\"op\":\"help\"} for the full op catalog. "
        "Example: [{\"op\":\"lease_acquire\",\"agent_id\":\"agent\",\"task\":\"demo\",\"ttl_sec\":120},"
        "{\"op\":\"launch\",\"app\":\"notepad\"},{\"op\":\"type\",\"text\":\"hi\"},{\"op\":\"lease_release\"}]. "
        "Hard rules: confirm=true for destructive OS ops; never kill anti-cheat; compact responses by default."
    )
