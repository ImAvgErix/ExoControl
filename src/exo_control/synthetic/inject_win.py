"""Windows synthetic injection via SendInput + optional window messages."""
from __future__ import annotations
import sys
import time
from typing import Optional, Tuple

IS_WIN = sys.platform == "win32"

if IS_WIN:
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    INPUT_MOUSE = 0
    INPUT_KEYBOARD = 1
    MOUSEEVENTF_MOVE = 0x0001
    MOUSEEVENTF_LEFTDOWN = 0x0002
    MOUSEEVENTF_LEFTUP = 0x0004
    MOUSEEVENTF_RIGHTDOWN = 0x0008
    MOUSEEVENTF_RIGHTUP = 0x0010
    MOUSEEVENTF_ABSOLUTE = 0x8000
    MOUSEEVENTF_VIRTUALDESK = 0x4000
    MOUSEEVENTF_WHEEL = 0x0800
    MOUSEEVENTF_HWHEEL = 0x1000
    MOUSEEVENTF_MIDDLEDOWN = 0x0020
    MOUSEEVENTF_MIDDLEUP = 0x0040
    WHEEL_DELTA = 120
    KEYEVENTF_KEYUP = 0x0002
    KEYEVENTF_UNICODE = 0x0004
    WM_LBUTTONDOWN = 0x0201
    WM_LBUTTONUP = 0x0202
    WM_CHAR = 0x0102
    MK_LBUTTON = 0x0001

    class MOUSEINPUT(ctypes.Structure):
        _fields_ = [
            ("dx", wintypes.LONG),
            ("dy", wintypes.LONG),
            ("mouseData", wintypes.DWORD),
            ("dwFlags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
        ]

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [
            ("wVk", wintypes.WORD),
            ("wScan", wintypes.WORD),
            ("dwFlags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
        ]

    class HARDWAREINPUT(ctypes.Structure):
        _fields_ = [
            ("uMsg", wintypes.DWORD),
            ("wParamL", wintypes.WORD),
            ("wParamH", wintypes.WORD),
        ]

    class INPUT_UNION(ctypes.Union):
        _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]

    class INPUT(ctypes.Structure):
        _fields_ = [("type", wintypes.DWORD), ("union", INPUT_UNION)]

    def _screen_size() -> Tuple[int, int]:
        return user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)

    def move_abs(x: int, y: int) -> bool:
        sw, sh = _screen_size()
        if sw <= 1 or sh <= 1:
            return False
        ax = int(x * 65535 / max(sw - 1, 1))
        ay = int(y * 65535 / max(sh - 1, 1))
        inp = INPUT()
        inp.type = INPUT_MOUSE
        inp.union.mi = MOUSEINPUT(ax, ay, 0, MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK, 0, None)
        return user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT)) == 1

    def click_abs(x: int, y: int, button: str = "left", clicks: int = 1) -> bool:
        if not move_abs(x, y):
            return False
        time.sleep(0.01)
        btn = (button or "left").lower()
        if btn in {"right", "r"}:
            down, up = MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP
        elif btn in {"middle", "mid", "m"}:
            down, up = 0x0020, 0x0040  # MOUSEEVENTF_MIDDLEDOWN / UP
        else:
            down, up = MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP
        n = max(1, min(3, int(clicks or 1)))
        for i in range(n):
            for flag in (down, up):
                inp = INPUT()
                inp.type = INPUT_MOUSE
                inp.union.mi = MOUSEINPUT(0, 0, 0, flag, 0, None)
                if user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT)) != 1:
                    return False
                time.sleep(0.01)
            if i + 1 < n:
                time.sleep(0.04)
        return True

    def cursor_pos() -> Optional[Tuple[int, int]]:
        pt = wintypes.POINT()
        if user32.GetCursorPos(ctypes.byref(pt)):
            return int(pt.x), int(pt.y)
        return None

    def move_human(x: int, y: int, duration: float = 0.07) -> bool:
        """Ease the pointer to (x,y) instead of teleporting (hover menus, wheel aim)."""
        start = cursor_pos()
        tx, ty = int(x), int(y)
        if not start:
            return move_abs(tx, ty)
        x0, y0 = start
        dist = ((tx - x0) ** 2 + (ty - y0) ** 2) ** 0.5
        if dist < 5:
            return move_abs(tx, ty)
        n = max(3, min(16, int(dist / 36)))
        dt = max(0.004, float(duration) / n)
        ok = True
        for i in range(1, n + 1):
            t = i / n
            e = 1.0 - (1.0 - t) ** 2
            ok = move_abs(int(x0 + (tx - x0) * e), int(y0 + (ty - y0) * e)) and ok
            time.sleep(dt)
        return move_abs(tx, ty) and ok

    def _wheel_dword(notches: int) -> int:
        # Positive notches = page down = Windows wheel toward user = negative delta.
        delta = -int(notches) * WHEEL_DELTA
        return delta & 0xFFFFFFFF

    def _send_wheel(notches: int, horizontal: bool) -> bool:
        if not notches:
            return True
        inp = INPUT()
        inp.type = INPUT_MOUSE
        flag = MOUSEEVENTF_HWHEEL if horizontal else MOUSEEVENTF_WHEEL
        inp.union.mi = MOUSEINPUT(0, 0, _wheel_dword(int(notches)), flag, 0, None)
        return user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT)) == 1

    def wheel_abs(
        x: int,
        y: int,
        notches: int = 0,
        h_notches: int = 0,
        *,
        per_notch: bool = True,
        human: bool = True,
    ) -> bool:
        """Move to (x,y) then send wheel ticks. Positive notches = scroll page down.

        One SendInput per notch — many apps ignore a single huge mouseData delta.
        """
        mover = move_human if human else move_abs
        if not mover(int(x), int(y)):
            return False
        time.sleep(0.02)
        nv = max(-40, min(40, int(notches)))
        nh = max(-40, min(40, int(h_notches)))
        ok = True
        if per_notch and abs(nv) > 1:
            sign = 1 if nv > 0 else -1
            for _ in range(abs(nv)):
                ok = _send_wheel(sign, False) and ok
                time.sleep(0.016)
        elif nv:
            ok = _send_wheel(nv, False) and ok
        if per_notch and abs(nh) > 1:
            sign = 1 if nh > 0 else -1
            for _ in range(abs(nh)):
                ok = _send_wheel(sign, True) and ok
                time.sleep(0.016)
        elif nh:
            ok = _send_wheel(nh, True) and ok
        return ok

    _MOUSE_FLAGS = {
        "left": (MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP),
        "right": (MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP),
        "middle": (MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP),
    }

    _VK = {
        "backspace": 0x08, "tab": 0x09, "enter": 0x0D, "return": 0x0D,
        "shift": 0x10, "ctrl": 0x11, "control": 0x11, "alt": 0x12,
        "pause": 0x13, "capslock": 0x14, "caps": 0x14, "esc": 0x1B, "escape": 0x1B,
        "space": 0x20, "pageup": 0x21, "pagedown": 0x22, "end": 0x23, "home": 0x24,
        "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28,
        "insert": 0x2D, "delete": 0x2E,
        "win": 0x5B, "lwin": 0x5B, "rwin": 0x5C, "apps": 0x5D,
    }
    for _i in range(1, 13):
        _VK[f"f{_i}"] = 0x70 + _i - 1
    for _i, _ch in enumerate("0123456789"):
        _VK[_ch] = 0x30 + _i
    for _i, _ch in enumerate("abcdefghijklmnopqrstuvwxyz"):
        _VK[_ch] = 0x41 + _i

    def mouse_button(button: str = "left", action: str = "click") -> bool:
        pair = _MOUSE_FLAGS.get((button or "left").lower())
        if not pair:
            return False
        down, up = pair
        act = (action or "click").lower()
        flags = []
        if act in {"down", "click"}:
            flags.append(down)
        if act in {"up", "click"}:
            flags.append(up)
        if not flags:
            return False
        for flag in flags:
            inp = INPUT()
            inp.type = INPUT_MOUSE
            inp.union.mi = MOUSEINPUT(0, 0, 0, flag, 0, None)
            if user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT)) != 1:
                return False
            time.sleep(0.01)
        return True

    def vk_code(name: str) -> Optional[int]:
        key = str(name or "").strip().lower()
        if not key:
            return None
        return _VK.get(key)

    def _send_key(vk: int, up: bool) -> bool:
        inp = INPUT()
        inp.type = INPUT_KEYBOARD
        inp.union.ki = KEYBDINPUT(int(vk), 0, KEYEVENTF_KEYUP if up else 0, 0, None)
        return user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT)) == 1

    def key_event(name: str, action: str = "tap") -> bool:
        vk = vk_code(name)
        if vk is None:
            return False
        act = (action or "tap").lower()
        if act not in {"down", "up", "tap"}:
            return False
        if act in {"down", "tap"} and not _send_key(vk, False):
            return False
        if act in {"up", "tap"} and not _send_key(vk, True):
            return False
        return True

    def wheel_here(notches: int = 0, h_notches: int = 0) -> bool:
        ok = True
        if notches:
            ok = _send_wheel(int(notches), False) and ok
        if h_notches:
            ok = _send_wheel(int(h_notches), True) and ok
        return ok

    def type_unicode(text: str) -> bool:
        ok = True
        for ch in text:
            for flags in (KEYEVENTF_UNICODE, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP):
                inp = INPUT()
                inp.type = INPUT_KEYBOARD
                inp.union.ki = KEYBDINPUT(0, ord(ch), flags, 0, None)
                if user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT)) != 1:
                    ok = False
            time.sleep(0.005)
        return ok

    def post_click_hwnd(hwnd: int, x: int, y: int) -> bool:
        """Click in window client coords without necessarily focusing (best-effort background)."""
        try:
            lparam = (y << 16) | (x & 0xFFFF)
            user32.PostMessageW(hwnd, WM_LBUTTONDOWN, MK_LBUTTON, lparam)
            time.sleep(0.02)
            user32.PostMessageW(hwnd, WM_LBUTTONUP, 0, lparam)
            return True
        except Exception:
            return False

    def window_rect(hwnd: int) -> Optional[Tuple[int, int, int, int]]:
        rect = wintypes.RECT()
        if user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            return rect.left, rect.top, rect.right, rect.bottom
        return None

else:
    def move_abs(x, y): return False
    def click_abs(x, y, button="left"): return False
    def cursor_pos(): return None
    def move_human(x, y, duration=0.07): return False
    def wheel_abs(x, y, notches=0, h_notches=0, **kwargs): return False
    def type_unicode(text): return False
    def mouse_button(button="left", action="click"): return False
    def vk_code(name): return None
    def key_event(name, action="tap"): return False
    def wheel_here(notches=0, h_notches=0): return False
    def post_click_hwnd(hwnd, x, y): return False
    def window_rect(hwnd): return None
