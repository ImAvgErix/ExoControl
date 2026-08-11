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
