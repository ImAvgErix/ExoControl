"""
macOS Accessibility (AX) helpers + CGEvent injection refinements.
Requires: accessibility permission for the terminal/app running the driver.
"""
from __future__ import annotations
import sys
from typing import Any, Dict, List, Optional, Tuple

IS_MAC = sys.platform == "darwin"


def list_ax_windows() -> List[Dict[str, Any]]:
    if not IS_MAC:
        return []
    try:
        from ApplicationServices import (
            AXUIElementCreateSystemWide,
            AXUIElementCopyAttributeValue,
            kAXWindowsAttribute,
            kAXTitleAttribute,
            kAXPIDAttribute,
        )
        # Fallback via AppKit running apps
        from AppKit import NSWorkspace
        out = []
        for app in NSWorkspace.sharedWorkspace().runningApplications():
            try:
                out.append({
                    "title": str(app.localizedName() or ""),
                    "pid": int(app.processIdentifier()),
                    "bundle": str(app.bundleIdentifier() or ""),
                    "active": bool(app.isActive()),
                })
            except Exception:
                continue
        return out
    except Exception:
        return []


def ax_press(pid: int, role_hint: str = "", title_hint: str = "") -> Tuple[bool, str]:
    """Best-effort AXPress on first matching element under app pid."""
    if not IS_MAC:
        return False, "not macOS"
    try:
        from ApplicationServices import (
            AXUIElementCreateApplication,
            AXUIElementCopyAttributeValue,
            AXUIElementPerformAction,
            kAXChildrenAttribute,
            kAXRoleAttribute,
            kAXTitleAttribute,
            kAXPressAction,
        )
        app = AXUIElementCreateApplication(pid)
        # BFS children limited depth
        queue = [app]
        seen = 0
        while queue and seen < 200:
            el = queue.pop(0)
            seen += 1
            try:
                err, role = AXUIElementCopyAttributeValue(el, kAXRoleAttribute, None)
                role_s = str(role or "")
                err2, title = AXUIElementCopyAttributeValue(el, kAXTitleAttribute, None)
                title_s = str(title or "")
                match_role = not role_hint or role_hint.lower() in role_s.lower()
                match_title = not title_hint or title_hint.lower() in title_s.lower()
                if match_role and match_title and (role_hint or title_hint):
                    err3 = AXUIElementPerformAction(el, kAXPressAction)
                    if err3 == 0:
                        return True, f"AXPress {role_s}:{title_s}"
                errc, children = AXUIElementCopyAttributeValue(el, kAXChildrenAttribute, None)
                if children:
                    queue.extend(list(children)[:30])
            except Exception:
                continue
        return False, "no AX match"
    except Exception as e:
        return False, str(e)


def cgevent_click(x: float, y: float, button: str = "left") -> Tuple[bool, str]:
    if not IS_MAC:
        return False, "not macOS"
    try:
        from .inject_mac import click_abs
        ok = click_abs(int(x), int(y), button=button)
        return ok, "CGEvent click" if ok else "CGEvent failed"
    except Exception as e:
        return False, str(e)
