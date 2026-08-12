"""Linux synthetic injection — X11 XTEST best-effort."""
from __future__ import annotations
import sys
import time
from typing import Optional

IS_LINUX = sys.platform.startswith("linux")

def click_abs(x: int, y: int, button: str = "left") -> bool:
    if not IS_LINUX:
        return False
    # Try xdotool
    import shutil, subprocess
    if shutil.which("xdotool"):
        btn = "1" if button == "left" else "3"
        r = subprocess.run(["xdotool", "mousemove", str(int(x)), str(int(y)), "click", btn], capture_output=True)
        return r.returncode == 0
    # Try python-xlib XTTest
    try:
        from Xlib import display, X
        from Xlib.ext import xtest
        d = display.Display()
        xtest.fake_input(d, X.MotionNotify, x=int(x), y=int(y))
        d.sync()
        b = 1 if button == "left" else 3
        xtest.fake_input(d, X.ButtonPress, b)
        d.sync()
        time.sleep(0.02)
        xtest.fake_input(d, X.ButtonRelease, b)
        d.sync()
        return True
    except Exception:
        return False

def type_text(text: str) -> bool:
    if not IS_LINUX:
        return False
    import shutil, subprocess
    if shutil.which("xdotool"):
        r = subprocess.run(["xdotool", "type", "--clearmodifiers", "--", text], capture_output=True)
        return r.returncode == 0
    return False

def wheel_abs(x: int, y: int, notches: int = 0, h_notches: int = 0, **kwargs) -> bool:
    """xdotool: button 5 = page down, 4 = page up. Positive notches = page down."""
    if not IS_LINUX:
        return False
    import shutil, subprocess
    if not shutil.which("xdotool"):
        return False
    if not move_abs(int(x), int(y)):
        return False
    ok = True
    nv = max(-40, min(40, int(notches)))
    btn = "5" if nv > 0 else "4"
    for _ in range(abs(nv)):
        r = subprocess.run(["xdotool", "click", btn], capture_output=True)
        ok = r.returncode == 0 and ok
    nh = max(-40, min(40, int(h_notches)))
    hbtn = "7" if nh > 0 else "6"
    for _ in range(abs(nh)):
        r = subprocess.run(["xdotool", "click", hbtn], capture_output=True)
        ok = r.returncode == 0 and ok
    return ok


def move_abs(x: int, y: int) -> bool:
    if not IS_LINUX:
        return False
    import shutil, subprocess
    if shutil.which("xdotool"):
        r = subprocess.run(["xdotool", "mousemove", str(int(x)), str(int(y))], capture_output=True)
        return r.returncode == 0
    try:
        from Xlib import display, X
        from Xlib.ext import xtest
        d = display.Display()
        xtest.fake_input(d, X.MotionNotify, x=int(x), y=int(y))
        d.sync()
        return True
    except Exception:
        return False
