"""
Aether Driver - Action Layer (Hands)
Cross-platform mouse/keyboard via pynput. 
Note: This moves the real cursor (reliable but not background).
For true background synthetic cursors, integrate Cua Driver, xa11y, or platform HID.
"""

from __future__ import annotations
import time
from typing import Any, Dict, List, Optional, Tuple, Union

try:
    from pynput.mouse import Button, Controller as MouseController
    from pynput.keyboard import Key, Controller as KeyboardController, KeyCode
    HAS_PYNPUT = True
except ImportError:
    HAS_PYNPUT = False

try:
    import pyautogui
    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.05
    HAS_PYAUTOGUI = True
except Exception:
    # ImportError or missing DISPLAY
    HAS_PYAUTOGUI = False


class ActionEngine:
    """Hands for Aether Driver. Prefer element targets when available."""

    def __init__(self, backend: str = "pynput", failsafe: bool = True):
        self.backend = backend
        self.failsafe = failsafe
        self.mouse = None
        self.keyboard = None
        self.action_log: List[Dict] = []
        if HAS_PYNPUT:
            self.mouse = MouseController()
            self.keyboard = KeyboardController()
        if not HAS_PYNPUT and not HAS_PYAUTOGUI:
            print("Warning: pynput/pyautogui unavailable — local hands disabled")

    @staticmethod
    def _to_key(name: str):
        """Resolve a key name to a pynput Key.

        Only modifiers used to be mapped, so pynput was handed the raw string
        'esc' and raised — every named key silently failed.
        """
        if not HAS_PYNPUT:
            return name
        k = str(name).strip().lower()
        aliases = {
            "control": "ctrl", "ctl": "ctrl", "command": "cmd", "win": "cmd",
            "windows": "cmd", "super": "cmd", "return": "enter", "escape": "esc",
            "del": "delete", "ins": "insert", "pgup": "page_up", "pgdn": "page_down",
            "pageup": "page_up", "pagedown": "page_down", "capslock": "caps_lock",
            "printscreen": "print_screen", "numlock": "num_lock",
            "scrolllock": "scroll_lock", "bksp": "backspace", "spacebar": "space",
            "arrowup": "up", "arrowdown": "down", "arrowleft": "left",
            "arrowright": "right",
        }
        k = aliases.get(k, k)
        member = getattr(Key, k, None)
        if member is not None:
            return member
        if len(k) == 1:
            return k
        return KeyCode.from_char(name) if len(str(name)) == 1 else name

    def _log(self, action: str, details: Dict, success: bool = True):
        entry = {
            "time": time.time(),
            "action": action,
            "details": details,
            "success": success,
        }
        self.action_log.append(entry)
        return entry

    def get_position(self) -> Tuple[int, int]:
        if self.mouse:
            pos = self.mouse.position
            return (int(pos[0]), int(pos[1]))
        if HAS_PYAUTOGUI:
            return pyautogui.position()
        return (0, 0)

    def move(self, x: int, y: int, duration: float = 0.15) -> Dict:
        try:
            if self.backend == "pynput" and self.mouse:
                # pynput is instantaneous; optional smooth later
                self.mouse.position = (x, y)
            elif HAS_PYAUTOGUI:
                pyautogui.moveTo(x, y, duration=duration)
            return self._log("move", {"x": x, "y": y}, True)
        except Exception as e:
            return self._log("move", {"x": x, "y": y, "error": str(e)}, False)

    def click(
        self,
        x: Optional[int] = None,
        y: Optional[int] = None,
        button: str = "left",
        clicks: int = 1,
        target: Optional[Dict] = None,
    ) -> Dict:
        """
        Click at coords or center of a target element (from observe).
        target example: {"bbox": [x1,y1,x2,y2]} or {"center": [x,y]}
        """
        if target:
            if "center" in target:
                x, y = target["center"]
            elif "bbox" in target:
                b = target["bbox"]
                x = (b[0] + b[2]) // 2
                y = (b[1] + b[3]) // 2
        if x is None or y is None:
            return self._log("click", {"error": "No coordinates or target"}, False)

        try:
            btn = Button.left
            if button == "right":
                btn = Button.right
            elif button == "middle":
                btn = Button.middle

            if self.backend == "pynput" and self.mouse:
                self.mouse.position = (x, y)
                time.sleep(0.05)
                for _ in range(clicks):
                    self.mouse.click(btn)
                    time.sleep(0.05)
            elif HAS_PYAUTOGUI:
                pyautogui.click(x=x, y=y, button=button, clicks=clicks)
            return self._log("click", {"x": x, "y": y, "button": button, "clicks": clicks}, True)
        except Exception as e:
            return self._log("click", {"x": x, "y": y, "error": str(e)}, False)

    def type_text(self, text: str, interval: float = 0.02, clear: bool = False) -> Dict:
        try:
            if clear:
                self.hotkey("ctrl", "a")
                time.sleep(0.05)
            if self.backend == "pynput" and self.keyboard:
                for char in text:
                    self.keyboard.type(char)
                    time.sleep(interval)
            elif HAS_PYAUTOGUI:
                pyautogui.write(text, interval=interval)
            return self._log("type", {"text": text[:50] + ("..." if len(text) > 50 else ""), "len": len(text)}, True)
        except Exception as e:
            return self._log("type", {"error": str(e)}, False)

    def press(self, key: str) -> Dict:
        """Press a special key: enter, tab, esc, etc."""
        try:
            key_map = {
                "enter": Key.enter,
                "return": Key.enter,
                "tab": Key.tab,
                "esc": Key.esc,
                "escape": Key.esc,
                "space": Key.space,
                "backspace": Key.backspace,
                "delete": Key.delete,
                "up": Key.up,
                "down": Key.down,
                "left": Key.left,
                "right": Key.right,
                "home": Key.home,
                "end": Key.end,
                "page_up": Key.page_up,
                "page_down": Key.page_down,
            }
            if self.backend == "pynput" and self.keyboard:
                k = key_map.get(key.lower())
                if k:
                    self.keyboard.press(k)
                    self.keyboard.release(k)
                else:
                    self.keyboard.press(key)
                    self.keyboard.release(key)
            elif HAS_PYAUTOGUI:
                pyautogui.press(key)
            return self._log("press", {"key": key}, True)
        except Exception as e:
            return self._log("press", {"key": key, "error": str(e)}, False)

    def hotkey(self, *keys: str) -> Dict:
        try:
            if self.backend == "pynput" and self.keyboard:
                mapped = [self._to_key(k) for k in keys]
                # press all, release reverse
                for k in mapped:
                    self.keyboard.press(k)
                for k in reversed(mapped):
                    self.keyboard.release(k)
            elif HAS_PYAUTOGUI:
                pyautogui.hotkey(*keys)
            return self._log("hotkey", {"keys": list(keys)}, True)
        except Exception as e:
            return self._log("hotkey", {"keys": list(keys), "error": str(e)}, False)

    def scroll(self, dx: int = 0, dy: int = 0, x: Optional[int] = None, y: Optional[int] = None) -> Dict:
        try:
            if x is not None and y is not None:
                self.move(x, y)
            if self.backend == "pynput" and self.mouse:
                self.mouse.scroll(dx, dy)
            elif HAS_PYAUTOGUI:
                pyautogui.scroll(dy)  # pyautogui mainly vertical
            return self._log("scroll", {"dx": dx, "dy": dy}, True)
        except Exception as e:
            return self._log("scroll", {"error": str(e)}, False)

    def drag(self, start: Tuple[int, int], end: Tuple[int, int], duration: float = 0.3) -> Dict:
        try:
            if self.backend == "pynput" and self.mouse:
                self.mouse.position = start
                time.sleep(0.05)
                self.mouse.press(Button.left)
                # simple linear for prototype
                steps = max(5, int(duration * 30))
                for i in range(1, steps + 1):
                    t = i / steps
                    cx = int(start[0] + (end[0] - start[0]) * t)
                    cy = int(start[1] + (end[1] - start[1]) * t)
                    self.mouse.position = (cx, cy)
                    time.sleep(duration / steps)
                self.mouse.release(Button.left)
            elif HAS_PYAUTOGUI:
                pyautogui.moveTo(*start)
                pyautogui.dragTo(*end, duration=duration, button="left")
            return self._log("drag", {"start": start, "end": end}, True)
        except Exception as e:
            return self._log("drag", {"error": str(e)}, False)

    def get_log(self, last_n: int = 20) -> List[Dict]:
        return self.action_log[-last_n:]
