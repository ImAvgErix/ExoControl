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
    {"op": "eyes_start", "aliases": [], "lease": False,
     "purpose": "Start live eyes loop (also auto on lease_acquire)", "fields": ["fps?", "ocr_on_change?"]},
    {"op": "eyes_stop", "aliases": [], "lease": False,
     "purpose": "Stop live eyes loop", "fields": []},
    {"op": "eyes_read", "aliases": ["look", "glance"], "lease": False,
     "purpose": "Glance at focused window (title + compact labels)", "fields": ["ocr?"]},
    {"op": "apps", "aliases": [], "lease": False, "purpose": "Running apps pid/title/exe", "fields": ["max?"]},
    {"op": "cdp", "aliases": ["cdp_discover", "exo_cdp"], "lease": False,
     "purpose": "Discover DevTools endpoints (Chrome/Edge/Exo WebView2)", "fields": ["port?"]},
    {"op": "wait_cdp", "aliases": ["wait_for_cdp"], "lease": False,
     "purpose": "Poll until CDP is up", "fields": ["timeout?", "port?", "poll?"]},
    {"op": "clipboard_get", "aliases": [], "lease": False, "purpose": "Read clipboard text", "fields": []},
    {"op": "notify", "aliases": [], "lease": True,
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
     "purpose": "Clear lease by token, holder agent_id, or EXO_ALLOW_FORCE_RELEASE=1",
     "fields": ["token?", "agent_id?"]},
    {"op": "files_list", "aliases": [], "lease": False,
     "purpose": "List dir under allowroot", "fields": ["path", "max?", "confirm?"]},
    {"op": "files_read", "aliases": [], "lease": False, "purpose": "Read text file under allowroot", "fields": ["path"]},
    {"op": "registry_read", "aliases": [], "lease": False, "purpose": "Read registry values at path", "fields": ["path", "max?"]},
    {"op": "proc_list", "aliases": [], "lease": False, "purpose": "Process inventory", "fields": ["max?"]},
    {"op": "service_list", "aliases": [], "lease": False, "purpose": "Windows services", "fields": []},
    {"op": "service_status", "aliases": [], "lease": False, "purpose": "One service status", "fields": ["name"]},
    {"op": "env_get", "aliases": [], "lease": False, "purpose": "Env var", "fields": ["name"]},
    {"op": "env_list", "aliases": [], "lease": False, "purpose": "Env var names (values via env_get)", "fields": ["max?"]},
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
    {"op": "fill", "aliases": [], "lease": True,
     "purpose": "Fill fields {label: value} or query+text sugar",
     "fields": ["fields?", "query?", "text?", "submit?", "confirm?"]},
    {"op": "scroll", "aliases": ["smart_scroll"], "lease": True,
     "purpose": "Aimed SendInput wheel (never Home/End). Positive = page down.",
     "fields": ["notches?", "direction?", "amount?", "dy?", "dx?", "query?"]},
    {"op": "scroll_into_view", "aliases": ["into_view"], "lease": True,
     "purpose": "Wheel until query/bbox is in the document viewport",
     "fields": ["query?", "bbox?", "max_steps?"]},
    {"op": "hover", "aliases": [], "lease": True,
     "purpose": "Move pointer like a person (hover menus/tooltips)",
     "fields": ["query?", "x?", "y?"]},
    {"op": "drag", "aliases": ["smart_drag"], "lease": True, "purpose": "Drag", "fields": ["x1", "y1", "x2", "y2"]},
    {"op": "hotkey", "aliases": ["smart_hotkey", "keys", "press"], "lease": True,
     "purpose": "Hotkey chord", "fields": ["keys"]},
    {"op": "screenshot", "aliases": ["shot"], "lease": True,
     "purpose": "JPEG/path capture; monitor/title bind fail-closed", "fields": ["title?", "monitor?", "path?", "max_side?"]},
    {"op": "launch", "aliases": ["start", "run"], "lease": True,
     "purpose": "Fuzzy app launch + wait_ready default for app names",
     "fields": ["app?", "name?", "command?", "wait_ready?", "title?", "timeout?", "args?", "focus?", "confirm?"]},
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
    {"op": "browser_scroll", "aliases": [], "lease": True,
     "purpose": "Scroll the page document (DOM scrollBy, not chrome)",
     "fields": ["dy?", "dx?", "notches?", "direction?", "query?", "selector?", "ref?", "space_id?"]},
    {"op": "browser_scroll_into_view", "aliases": ["browser_into_view"], "lease": True,
     "purpose": "DOM scrollIntoView for text/selector/ref",
     "fields": ["text?", "selector?", "ref?", "space_id?"]},
    {"op": "browser_hover", "aliases": [], "lease": True,
     "purpose": "Hover a page element", "fields": ["text?", "selector?", "ref?", "space_id?"]},
    {"op": "browser_wait", "aliases": [], "lease": True,
     "purpose": "Wait for text/name", "fields": ["text?", "name?", "timeout?", "space_id?"]},
    {"op": "browser_fill", "aliases": [], "lease": True, "purpose": "Fill form fields", "fields": ["fields", "space_id?"]},
    {"op": "browser_eval", "aliases": [], "lease": True,
     "purpose": "Evaluate JS (confirm required; EXO_DENY_BROWSER_EVAL=1 hard-denies)",
     "fields": ["js", "space_id?", "confirm"]},
    {"op": "browser_close_space", "aliases": [], "lease": True, "purpose": "Close space", "fields": ["space_id"]},
    {"op": "cursor_exec", "aliases": ["cursor_run"], "lease": True,
     "purpose": "Run steps on a named virtual cursor", "fields": ["cursor_id?", "steps"]},
    {"op": "create_cursor", "aliases": ["cursor_create"], "lease": True,
     "purpose": "Create a named virtual cursor", "fields": ["cursor_id?"]},
    {"op": "list_cursors", "aliases": ["cursors"], "lease": False,
     "purpose": "List virtual cursors", "fields": []},
]

HARNESS_RULES: List[str] = [
    "Works with ANY AI via MCP (stdio), CLI, or Python — not tied to one vendor.",
    "Script-first: prefer one batched exec with many steps over chatty single clicks.",
    "Acquire lease_acquire before hands (click/type/launch/browser/files write).",
    "You are a person in the chair: aim the pointer, wheel the document, glance after hands.",
    "Scroll with scroll / scroll_into_view / browser_scroll. Never Home/End (they jump the caret).",
    "Eyes first: observe/read/windows/verify; screenshots only when structure is insufficient.",
    "Hands attach a compact seen glance when live eyes are running (seen:false to skip).",
    "Compact by default; set verbose=true only when you need full trees.",
    "Focus by title; WinUI host ranks above WebView2 child windows.",
    "monitor=N binds focus/observe/shot to that display; wrong-monitor fails closed.",
    "confirm=true is an agent assertion, not a human prompt. Destructive OS ops still need it.",
    "Files outside EXO_FILE_ROOTS stay denied unless the operator sets EXO_ALLOW_OUTSIDE_ROOTS=1.",
    "lease_status never returns the token. force_release needs token, holder, or EXO_ALLOW_FORCE_RELEASE=1.",
    "Always lease_release when done (or let TTL expire).",
    "Never invent UI state — use step results / observe / verify / seen.",
]

MINIMAL_SCRIPT_EXAMPLE: List[Dict[str, Any]] = [
    {"op": "lease_acquire", "agent_id": "any-agent", "task": "demo", "ttl_sec": 120},
    {"op": "launch", "app": "notepad"},
    {"op": "focus", "title": "Notepad"},
    {"op": "type", "text": "hello from exo-control"},
    {"op": "notify", "title": "Exo Control", "body": "Done"},
    {"op": "lease_release"},
]


CORE_OPS = (
    "help", "status", "lease_acquire", "lease_release", "lease_status",
    "launch", "focus", "read", "observe", "click", "type", "scroll",
    "scroll_into_view", "hover", "verify", "wait", "screenshot",
)


def _names(entry: Dict[str, Any]) -> List[str]:
    return [entry["op"], *list(entry.get("aliases") or [])]


def lease_required_ops() -> frozenset:
    names = set()
    for entry in OPS:
        if entry.get("lease") in {True, "switch"}:
            names.update(_names(entry))
    return frozenset(names)


def lease_free_ops() -> frozenset:
    names = set()
    for entry in OPS:
        if entry.get("lease") is False:
            names.update(_names(entry))
    return frozenset(names)


def known_ops() -> frozenset:
    names = set()
    for entry in OPS:
        names.update(_names(entry))
    return frozenset(names)


def list_ops(*, query: Optional[str] = None, detail: bool = False, compact: Optional[bool] = None) -> Dict[str, Any]:
    q = (query or "").strip().lower()
    want_compact = compact if compact is not None else (not detail and not q)
    rows = []
    for entry in OPS:
        names = _names(entry)
        if q and not any(q in n for n in names) and q not in (entry.get("purpose") or "").lower():
            continue
        if want_compact and entry["op"] not in CORE_OPS:
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
    from exo_control.policy import identity

    ident = identity()
    return {
        "ok": True,
        "count": len(rows),
        "ops": rows,
        "compact": want_compact,
        "total_ops": len(OPS),
        "hint": "pass detail=true or query=… for the full catalog" if want_compact else None,
        "rules": list(HARNESS_RULES) if detail or q else HARNESS_RULES[:5],
        "example": list(MINIMAL_SCRIPT_EXAMPLE),
        "identity": ident,
        "surfaces": {
            "mcp": "python -m exo_control.slim_mcp_server",
            "cli": "exo-control exec",
            "python": "from exo_control import ExoExecEngine",
        },
        "tools": {
            "mcp": ["exo_exec", "exo_screenshot", "exo_help"],
            "note": "aether_* aliases only when EXO_MCP_ALIASES=1.",
        },
    }


def mcp_instructions() -> str:
    return (
        "Exo Control — realtime Windows eyes/hands for ANY AI harness (MCP/CLI/Python). "
        "Use exo_exec with a JSON array of steps. "
        "Always start mutating work with {\"op\":\"lease_acquire\",\"agent_id\":\"…\",\"task\":\"…\"} "
        "and end with lease_release. Prefer structure: focus → observe/read → click/type/scroll → verify. "
        "Scroll with aimed wheel (scroll / scroll_into_view / browser_scroll). Never Home/End. "
        "Hands attach a compact seen glance. Screenshots only when pixels matter (exo_screenshot). "
        "Call exo_help or step {\"op\":\"help\"} for ops (detail=true for the full catalog). "
        "Example: [{\"op\":\"lease_acquire\",\"agent_id\":\"agent\",\"task\":\"demo\",\"ttl_sec\":120},"
        "{\"op\":\"launch\",\"app\":\"notepad\"},{\"op\":\"type\",\"text\":\"hi\"},{\"op\":\"lease_release\"}]. "
        "Hard rules: confirm=true for destructive OS ops; never kill anti-cheat; compact by default; "
        "do not invent UI state."
    )
