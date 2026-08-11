"""macOS synthetic injection — CGEvent best-effort (focus may still change)."""
from __future__ import annotations
import sys
import time
from typing import Optional

IS_MAC = sys.platform == "darwin"

def click_abs(x: int, y: int, button: str = "left") -> bool:
    if not IS_MAC:
        return False
    try:
        from Quartz.CoreGraphics import (
            CGEventCreateMouseEvent, CGEventPost, CGEventCreate,
            kCGEventMouseMoved, kCGEventLeftMouseDown, kCGEventLeftMouseUp,
            kCGEventRightMouseDown, kCGEventRightMouseUp,
            kCGMouseButtonLeft, kCGMouseButtonRight, kCGHIDEventTap,
        )
        point = (float(x), float(y))
        move = CGEventCreateMouseEvent(None, kCGEventMouseMoved, point, kCGMouseButtonLeft)
        CGEventPost(kCGHIDEventTap, move)
        down_t = kCGEventLeftMouseDown if button == "left" else kCGEventRightMouseDown
        up_t = kCGEventLeftMouseUp if button == "left" else kCGEventRightMouseUp
        btn = kCGMouseButtonLeft if button == "left" else kCGMouseButtonRight
        down = CGEventCreateMouseEvent(None, down_t, point, btn)
        up = CGEventCreateMouseEvent(None, up_t, point, btn)
        CGEventPost(kCGHIDEventTap, down)
        time.sleep(0.02)
        CGEventPost(kCGHIDEventTap, up)
        return True
    except Exception:
        return False

def type_text(text: str) -> bool:
    if not IS_MAC:
        return False
    try:
        from Quartz.CoreGraphics import (
            CGEventCreateKeyboardEvent, CGEventPost, CGEventKeyboardSetUnicodeString,
            kCGHIDEventTap,
        )
        for ch in text:
            ev = CGEventCreateKeyboardEvent(None, 0, True)
            CGEventKeyboardSetUnicodeString(ev, len(ch), ch)
            CGEventPost(kCGHIDEventTap, ev)
            ev_up = CGEventCreateKeyboardEvent(None, 0, False)
            CGEventKeyboardSetUnicodeString(ev_up, len(ch), ch)
            CGEventPost(kCGHIDEventTap, ev_up)
            time.sleep(0.005)
        return True
    except Exception:
        return False

def move_abs(x: int, y: int) -> bool:
    if not IS_MAC:
        return False
    try:
        from Quartz.CoreGraphics import (
            CGEventCreateMouseEvent, CGEventPost,
            kCGEventMouseMoved, kCGMouseButtonLeft, kCGHIDEventTap,
        )
        move = CGEventCreateMouseEvent(None, kCGEventMouseMoved, (float(x), float(y)), kCGMouseButtonLeft)
        CGEventPost(kCGHIDEventTap, move)
        return True
    except Exception:
        return False
