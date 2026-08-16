"""
Windows accessibility backend via pywinauto + shared UIA cache.

Install: pip install pywinauto
Gives real UIA element listing + click/type by automation element on Windows.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from .backends import ActionBackend, DeliveryResult
from .uia_cache import get_uia_cache


class PywinautoBackend(ActionBackend):
    name = "pywinauto"

    def __init__(self):
        self._ready = False
        try:
            import pywinauto  # noqa: F401
            self._ready = True
        except Exception:
            self._ready = False

    def available(self) -> bool:
        return self._ready

    def list_windows(self) -> List[Dict[str, Any]]:
        if not self._ready:
            return []
        return get_uia_cache().list_windows()

    def get_window_state(self, pid: int, window_id: Optional[int] = None) -> Dict[str, Any]:
        if not self._ready:
            return {"ok": False, "error": "pywinauto not available", "elements": []}
        tree = get_uia_cache().get_tree(pid, window_id)
        if not tree.elements and not tree.title:
            return {"ok": False, "error": f"no window for pid={pid}", "elements": []}
        return tree.as_state()

    def _find_element(self, pid: int, element_index: int, window_id: Optional[int] = None):
        return get_uia_cache().get_element(pid, element_index, window_id)

    def click(self, x: Optional[int] = None, y: Optional[int] = None, button: str = "left",
              pid: Optional[int] = None, window_id: Optional[int] = None,
              element_index: Optional[int] = None, **kwargs) -> DeliveryResult:
        if not self._ready:
            return DeliveryResult(False, "pywinauto", "not available")
        try:
            clicks = int(kwargs.get("clicks") or 1)
            btn = (button or "left").lower()
            use_invoke = btn in {"left", "l"} and clicks <= 1
            if pid is not None and element_index is not None:
                el = self._find_element(pid, element_index, window_id)
                if el is None:
                    return DeliveryResult(False, "pywinauto", "element not found")
                if not use_invoke:
                    try:
                        r = el.rectangle()
                        cx = (int(r.left) + int(r.right)) // 2
                        cy = (int(r.top) + int(r.bottom)) // 2
                        from pywinauto import mouse
                        mouse.click(button=btn if btn != "l" else "left", coords=(cx, cy), click_count=max(1, clicks))
                        return DeliveryResult(
                            True, "pywinauto",
                            f"{btn} x{clicks} element_index={element_index}",
                            element_index=element_index,
                        )
                    except Exception:
                        pass
                if use_invoke:
                    for method in ("invoke", "click", "click_input"):
                        fn = getattr(el, method, None)
                        if callable(fn):
                            try:
                                fn()
                                return DeliveryResult(
                                    True, "pywinauto",
                                    f"clicked element_index={element_index} via {method}",
                                    element_index=element_index,
                                )
                            except Exception:
                                continue
                return DeliveryResult(False, "pywinauto", "element methods failed")
            if x is not None and y is not None:
                from pywinauto import mouse
                mouse.click(button=button, coords=(int(x), int(y)))
                return DeliveryResult(True, "pywinauto", f"coords=({x},{y})")
            return DeliveryResult(False, "pywinauto", "need element_index or x/y")
        except Exception as e:
            return DeliveryResult(False, "pywinauto", str(e))

    def type_text(self, text: str, **kwargs) -> DeliveryResult:
        if not self._ready:
            return DeliveryResult(False, "pywinauto", "not available")
        try:
            pid = kwargs.get("pid")
            element_index = kwargs.get("element_index")
            window_id = kwargs.get("window_id")
            if pid is not None and element_index is not None:
                el = self._find_element(pid, int(element_index), window_id)
                if el is not None:
                    try:
                        el.set_focus()
                    except Exception:
                        pass
                    el.type_keys(text, with_spaces=True, pause=0.01)
                    return DeliveryResult(True, "pywinauto", "typed into element")
            from pywinauto import keyboard
            keyboard.send_keys(text, with_spaces=True, pause=0.01)
            return DeliveryResult(True, "pywinauto", "typed to focus")
        except Exception as e:
            return DeliveryResult(False, "pywinauto", str(e))
