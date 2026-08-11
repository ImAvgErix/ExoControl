
"""
Windows UIA invoke patterns — click/toggle/expand via accessibility, not coords.
Uses shared UiaTreeCache so invoke does not re-walk the desktop every click.
Always hops to the STA marshal thread (safe from QueueHub cursor workers).
"""
from __future__ import annotations
from typing import Optional, Tuple

from .sta_marshal import call_on_sta


def _invoke_element_impl(pid: int, element_index: int, window_id: Optional[int] = None) -> Tuple[bool, str]:
    try:
        from aether.uia_cache import get_uia_cache
    except Exception as e:
        return False, f"uia_cache missing: {e}"
    try:
        cache = get_uia_cache()
        el = cache.get_element(pid, element_index, window_id)
        if el is None:
            return False, "element not found"
        for method in ("invoke", "toggle", "select", "click", "click_input"):
            fn = getattr(el, method, None)
            if callable(fn):
                try:
                    fn()
                    return True, f"uia:{method}"
                except Exception:
                    continue
        return False, "no invoke/toggle/select/click on element"
    except Exception as e:
        return False, str(e)


def invoke_element(pid: int, element_index: int, window_id: Optional[int] = None) -> Tuple[bool, str]:
    return call_on_sta(_invoke_element_impl, pid, element_index, window_id)


def _set_value_impl(pid: int, element_index: int, value: str, window_id: Optional[int] = None) -> Tuple[bool, str]:
    try:
        from aether.uia_cache import get_uia_cache
        cache = get_uia_cache()
        el = cache.get_element(pid, element_index, window_id)
        if el is None:
            return False, "element not found"
        for method in ("set_edit_text", "set_text", "type_keys"):
            fn = getattr(el, method, None)
            if callable(fn):
                try:
                    if method == "type_keys":
                        fn(value, with_spaces=True)
                    else:
                        fn(value)
                    return True, f"uia:{method}"
                except Exception:
                    continue
        return False, "set_value failed"
    except Exception as e:
        return False, str(e)


def set_value(pid: int, element_index: int, value: str, window_id: Optional[int] = None) -> Tuple[bool, str]:
    return call_on_sta(_set_value_impl, pid, element_index, value, window_id)
