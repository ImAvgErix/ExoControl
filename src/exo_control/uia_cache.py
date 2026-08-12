"""
Shared Windows UIA tree cache — the #1 speed win for hands.

The naive walk cost ~5s per read because every element property (name, role,
rectangle) is a separate cross-process COM call: 220 elements x 3 props = 660
round-trips. This module batches the whole subtree into one FindAllBuildCache
call so property reads become local memory reads.

It also:
  - Enumerates top-level windows via EnumWindows instead of a UIA desktop walk
  - Caches resolved window roots per (pid, hwnd)
  - Drops offscreen elements at the UIA condition level
  - De-duplicates the Text/Button pairs WebView2 reports for one visual control
  - Publishes a ui_hash so callers can verify change without pixels
"""
from __future__ import annotations

import ctypes
import hashlib
import threading
import time
import warnings
from ctypes import wintypes
from typing import Any, Dict, List, Optional, Tuple

_STA_WARN_ONCE = False


def _import_pywinauto_quiet():
    """Import pywinauto without spamming STA COM warnings to agent stderr."""
    global _STA_WARN_ONCE
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        import pywinauto  # noqa: F401
        from pywinauto import Desktop  # noqa: F401
        from pywinauto.uia_defines import IUIA  # noqa: F401
        if caught and not _STA_WARN_ONCE:
            _STA_WARN_ONCE = True
            # One-line debug breadcrumb only (agents should not see floods).
            try:
                import logging
                logging.getLogger("exo_control.uia").debug(
                    "pywinauto STA mode: %s", caught[0].message
                )
            except Exception:
                pass
    return True

# Higher wins when two elements describe the same pixels. A Button beats the
# Text label drawn inside it, which is what makes clicks land on the control.
ROLE_PRIORITY: Dict[str, int] = {
    "button": 100,
    "splitbutton": 96,
    "menuitem": 92,
    "tabitem": 90,
    "hyperlink": 86,
    "listitem": 82,
    "treeitem": 78,
    "checkbox": 76,
    "radiobutton": 74,
    "combobox": 72,
    "edit": 70,
    "spinner": 60,
    "slider": 58,
    "custom": 40,
    "image": 30,
    "text": 20,
    "document": 12,
    "list": 10,
    "group": 6,
    "pane": 4,
    "window": 2,
}

INTERACTIVE_ROLES = frozenset({
    "button", "splitbutton", "menuitem", "tabitem", "hyperlink", "listitem",
    "treeitem", "checkbox", "radiobutton", "combobox", "edit", "slider", "spinner",
})

# Roles whose typed/document content agents need to read (Value/Text patterns).
CONTENT_ROLES = frozenset({
    "edit", "document", "text", "combobox", "spinner", "custom",
})


def _role_rank(role: str) -> int:
    return ROLE_PRIORITY.get((role or "").lower(), 35)


class CachedElement:
    """A UIA element with its properties already pulled local.

    `raw` is the IUIAutomationElement. The pywinauto wrapper is only built if
    someone actually acts on the element, because wrapper construction is the
    expensive part of a tree walk.
    """

    __slots__ = ("index", "name", "role", "bbox", "on_screen", "enabled",
                 "automation_id", "value", "value_via", "raw", "_live")

    def __init__(self, index: int, name: str, role: str, bbox: Optional[List[int]],
                 on_screen: bool = True, enabled: bool = True, automation_id: str = "",
                 value: str = "", value_via: str = "", raw: Any = None, live: Any = None):
        self.index = index
        self.name = name
        self.role = role
        self.bbox = bbox
        self.on_screen = on_screen
        self.enabled = enabled
        self.automation_id = automation_id
        self.value = value or ""
        self.value_via = value_via or ""
        self.raw = raw
        self._live = live

    @property
    def live(self):
        if self._live is None and self.raw is not None:
            self._live = _wrap_raw(self.raw)
        return self._live

    @live.setter
    def live(self, value):
        self._live = value

    @property
    def rank(self) -> int:
        return _role_rank(self.role)

    @property
    def center(self) -> Optional[Tuple[int, int]]:
        if not self.bbox or len(self.bbox) != 4:
            return None
        return (self.bbox[0] + self.bbox[2]) // 2, (self.bbox[1] + self.bbox[3]) // 2

    @property
    def text(self) -> str:
        """Best human-visible string for this node (name or value content)."""
        return (self.value or self.name or "").strip()

    def as_dict(self) -> Dict[str, Any]:
        out = {
            "element_index": self.index,
            "name": self.name,
            "role": self.role,
            "bbox": self.bbox,
            "on_screen": self.on_screen,
            "enabled": self.enabled,
        }
        if self.value:
            # Cap so compact_observe stays token-safe.
            out["value"] = self.value if len(self.value) <= 240 else (self.value[:237] + "...")
            if self.value_via:
                out["value_via"] = self.value_via
        return out


class CachedTree:
    __slots__ = ("pid", "window_id", "title", "elements", "by_name", "built_at",
                 "root", "ui_hash", "build_ms", "truncated")

    def __init__(self, pid: int, window_id: Optional[int], title: str = "",
                 elements: Optional[List[CachedElement]] = None,
                 by_name: Optional[Dict[str, List[int]]] = None,
                 built_at: float = 0.0, root: Any = None, ui_hash: str = "",
                 build_ms: int = 0, truncated: bool = False):
        self.pid = pid
        self.window_id = window_id
        self.title = title
        self.elements = elements if elements is not None else []
        self.by_name = by_name if by_name is not None else {}
        self.built_at = built_at
        self.root = root
        self.ui_hash = ui_hash
        self.build_ms = build_ms
        self.truncated = truncated

    def as_state(self) -> Dict[str, Any]:
        return {
            "ok": True,
            "pid": self.pid,
            "window_id": self.window_id,
            "title": self.title,
            "cached": True,
            "age_ms": int((time.time() - self.built_at) * 1000),
            "ui_hash": self.ui_hash,
            "elements": [e.as_dict() for e in self.elements],
        }


# ── Native window enumeration ────────────────────────────────────────

_user32 = ctypes.windll.user32 if hasattr(ctypes, "windll") else None
_WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


def virtual_screen() -> Tuple[int, int, int, int]:
    """(left, top, right, bottom) across all monitors."""
    if _user32 is None:
        return (0, 0, 1920, 1080)
    x = _user32.GetSystemMetrics(76)
    y = _user32.GetSystemMetrics(77)
    w = _user32.GetSystemMetrics(78)
    h = _user32.GetSystemMetrics(79)
    if w <= 0 or h <= 0:
        return (0, 0, _user32.GetSystemMetrics(0), _user32.GetSystemMetrics(1))
    return (x, y, x + w, y + h)


def _window_title(hwnd: int) -> str:
    n = _user32.GetWindowTextLengthW(hwnd)
    if n <= 0:
        return ""
    buf = ctypes.create_unicode_buffer(n + 1)
    _user32.GetWindowTextW(hwnd, buf, n + 1)
    return buf.value or ""


def _window_class(hwnd: int) -> str:
    buf = ctypes.create_unicode_buffer(256)
    _user32.GetClassNameW(hwnd, buf, 256)
    return buf.value or ""


def enum_top_windows(visible_only: bool = True) -> List[Dict[str, Any]]:
    """EnumWindows-based listing. Milliseconds, versus ~500ms for a UIA walk."""
    if _user32 is None:
        return []
    out: List[Dict[str, Any]] = []

    def _cb(hwnd, _lparam):
        try:
            visible = bool(_user32.IsWindowVisible(hwnd))
            if visible_only and not visible:
                return True
            title = _window_title(hwnd)
            if visible_only and not title:
                return True
            pid = wintypes.DWORD()
            _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            rect = wintypes.RECT()
            _user32.GetWindowRect(hwnd, ctypes.byref(rect))
            out.append({
                "title": title,
                "handle": int(hwnd),
                "pid": int(pid.value),
                "class_name": _window_class(hwnd),
                "visible": visible,
                "minimized": bool(_user32.IsIconic(hwnd)),
                "rect": [int(rect.left), int(rect.top), int(rect.right), int(rect.bottom)],
            })
        except Exception:
            pass
        return True

    try:
        _user32.EnumWindows(_WNDENUMPROC(_cb), 0)
    except Exception:
        return out
    return out


# ── Batched UIA property fetch ───────────────────────────────────────

class _FastUia:
    """Wraps IUIAutomation with a prebuilt cache request."""

    def __init__(self):
        self.ok = False
        self.iuia = None
        self._cache_req = None
        self._condition = None
        self._ct_names: Dict[int, str] = {}
        self._scope_descendants = 4
        self._scope_children = 2
        try:
            _import_pywinauto_quiet()
            from pywinauto.uia_defines import IUIA
            wrap = IUIA()
            self.iuia = wrap.iuia
            dll = wrap.UIA_dll
            self._scope_descendants = wrap.tree_scope.get("descendants", 4)
            req = self.iuia.CreateCacheRequest()
            for prop in ("UIA_NamePropertyId", "UIA_ControlTypePropertyId",
                         "UIA_BoundingRectanglePropertyId", "UIA_IsOffscreenPropertyId",
                         "UIA_IsEnabledPropertyId", "UIA_AutomationIdPropertyId"):
                try:
                    req.AddProperty(getattr(dll, prop))
                except Exception:
                    pass
            self._cache_req = req
            self._scope_children = wrap.tree_scope.get("children", 2)
            # Filter offscreen elements out in the UIA engine rather than in
            # Python — this is what used to leak -30000 coordinates to clicks.
            try:
                offscreen = self.iuia.CreatePropertyCondition(
                    dll.UIA_IsOffscreenPropertyId, True)
                self._condition = self.iuia.CreateNotCondition(offscreen)
            except Exception:
                self._condition = self.iuia.CreateTrueCondition()
            for attr in dir(dll):
                if attr.startswith("UIA_") and attr.endswith("ControlTypeId"):
                    try:
                        self._ct_names[int(getattr(dll, attr))] = attr[4:-13].lower()
                    except Exception:
                        continue
            self.ok = True
        except Exception:
            self.ok = False

    def role_name(self, ct_id: Any) -> str:
        try:
            return self._ct_names.get(int(ct_id), "")
        except Exception:
            return ""

    def element_from_handle(self, hwnd: int):
        if not self.ok:
            return None
        try:
            return self.iuia.ElementFromHandle(int(hwnd))
        except Exception:
            return None

    def _children(self, node) -> List[Any]:
        try:
            arr = node.FindAllBuildCache(
                self._scope_children, self._condition, self._cache_req)
            return [arr.GetElement(i) for i in range(int(arr.Length))]
        except Exception:
            return []

    def descendants(self, root, limit: int, max_nodes: int = 4000,
                    deadline_s: float = 1.5) -> Tuple[List[Any], bool]:
        """Breadth-first walk with budgets.

        Asking for TreeScope_Descendants in one call costs ~2.5s on a WebView2
        window, because the DOM publishes thousands of deep text nodes and the
        provider must walk all of them. Every control an agent can act on sits
        in the first hundred or so nodes breadth-first, so expand level by level
        and stop once the budget is met — measured at ~50ms for the same result.
        """
        if not self.ok or root is None:
            return [], False
        out: List[Any] = []
        frontier = [root]
        visited = 0
        useful = 0
        end_at = time.time() + deadline_s
        truncated = False
        while frontier:
            if visited >= max_nodes or time.time() >= end_at:
                truncated = True
                break
            level: List[Any] = []
            for node in frontier:
                level.extend(self._children(node))
                if visited + len(level) >= max_nodes:
                    truncated = True
                    break
            if not level:
                break
            visited += len(level)
            out.extend(level)
            for el in level:
                try:
                    if (el.CachedName or "").strip():
                        useful += 1
                except Exception:
                    continue
            if useful >= limit:
                truncated = True
                break
            frontier = level
        return out, truncated

    def descendants_full(self, root, limit: int) -> Tuple[List[Any], bool]:
        """Exhaustive subtree query — only worth it on small windows."""
        if not self.ok or root is None:
            return [], False
        try:
            arr = root.FindAllBuildCache(
                self._scope_descendants, self._condition, self._cache_req)
            total = int(arr.Length)
        except Exception:
            return [], False
        n = min(total, limit)
        out = []
        for i in range(n):
            try:
                out.append(arr.GetElement(i))
            except Exception:
                continue
        return out, total > limit

    def read(self, el) -> Optional[Tuple[str, str, Optional[List[int]], bool, bool, str]]:
        """Local reads off the cache — no round-trips."""
        try:
            name = (el.CachedName or "").strip()
        except Exception:
            name = ""
        try:
            role = self.role_name(el.CachedControlType)
        except Exception:
            role = ""
        bbox = None
        try:
            r = el.CachedBoundingRectangle
            left, top, right, bottom = int(r.left), int(r.top), int(r.right), int(r.bottom)
            if right > left and bottom > top:
                bbox = [left, top, right, bottom]
        except Exception:
            pass
        try:
            on_screen = not bool(el.CachedIsOffscreen)
        except Exception:
            on_screen = True
        try:
            enabled = bool(el.CachedIsEnabled)
        except Exception:
            enabled = True
        try:
            aid = el.CachedAutomationId or ""
        except Exception:
            aid = ""
        return name, role, bbox, on_screen, enabled, aid


_FAST: Optional[_FastUia] = None
_FAST_LOCK = threading.Lock()


def get_fast_uia() -> _FastUia:
    """Return process-wide fast UIA; construct on the STA thread (Windows)."""
    global _FAST
    try:
        from exo_control.synthetic.sta_marshal import call_on_sta, on_sta_thread
        if not on_sta_thread():
            return call_on_sta(get_fast_uia)
    except Exception:
        pass
    with _FAST_LOCK:
        if _FAST is None:
            _FAST = _FastUia()
        return _FAST


def _wrap_raw(raw):
    """Build a pywinauto wrapper on demand (only for elements we act on)."""
    try:
        from pywinauto.controls.uiawrapper import UIAWrapper
        from pywinauto.uia_element_info import UIAElementInfo
        return UIAWrapper(UIAElementInfo(raw))
    except Exception:
        return None


def read_element_value_meta(raw: Any, max_chars: int = 800) -> Tuple[str, str]:
    """Return ``(text, via)`` where via is value|text|legacy|win32|""."""
    if raw is None or max_chars <= 0:
        return "", ""
    try:
        _import_pywinauto_quiet()
        from pywinauto.uia_defines import IUIA
        dll = IUIA().UIA_dll
    except Exception:
        return "", ""

    # Never dump password-field contents.
    try:
        is_pw = bool(getattr(raw, "CurrentIsPassword", 0))
        if not is_pw:
            try:
                from pywinauto.uia_defines import IUIA as _IU
                pid_pw = getattr(_IU().UIA_dll, "UIA_IsPasswordPropertyId", None)
                if pid_pw is not None:
                    is_pw = bool(raw.GetCurrentPropertyValue(pid_pw))
            except Exception:
                pass
        if is_pw:
            return "••••", "password"
    except Exception:
        pass

    # Prefer ValuePattern (edit fields, many documents).
    try:
        iface = getattr(dll, "IUIAutomationValuePattern", None)
        pid = getattr(dll, "UIA_ValuePatternId", None)
        if iface is not None and pid is not None:
            pat = raw.GetCurrentPatternAs(pid, iface._iid_)
            if pat is not None:
                v = (getattr(pat, "CurrentValue", None) or "").strip()
                if v:
                    return v[:max_chars], "value"
    except Exception:
        pass

    # TextPattern — Win11 Notepad document, rich edits.
    try:
        iface = getattr(dll, "IUIAutomationTextPattern", None)
        pid = getattr(dll, "UIA_TextPatternId", None)
        if iface is not None and pid is not None:
            pat = raw.GetCurrentPatternAs(pid, iface._iid_)
            if pat is not None:
                try:
                    rng = pat.DocumentRange
                    if rng is not None:
                        v = (rng.GetText(int(max_chars)) or "").strip()
                        if v:
                            return v[:max_chars], "text"
                except Exception:
                    pass
    except Exception:
        pass

    # Legacy IAccessible value fallback.
    try:
        iface = getattr(dll, "IUIAutomationLegacyIAccessiblePattern", None)
        pid = getattr(dll, "UIA_LegacyIAccessiblePatternId", None)
        if iface is not None and pid is not None:
            pat = raw.GetCurrentPatternAs(pid, iface._iid_)
            if pat is not None:
                v = (getattr(pat, "CurrentValue", None) or "").strip()
                if v:
                    return v[:max_chars], "legacy"
    except Exception:
        pass
    return "", ""


def read_element_value(raw: Any, max_chars: int = 800) -> str:
    """Read document/edit content via Value, Text, or LegacyIAccessible patterns."""
    text, _via = read_element_value_meta(raw, max_chars=max_chars)
    return text


def win32_child_edit_texts(hwnd: int, max_chars: int = 4000) -> List[str]:
    """WM_GETTEXT on Edit/RichEdit child HWNDs (classic Notepad + many editors)."""
    if _user32 is None or not hwnd:
        return []
    WM_GETTEXT = 0x000D
    WM_GETTEXTLENGTH = 0x000E
    out: List[str] = []

    def _cb(child, _lp):
        try:
            cls = _window_class(int(child))
            cl = (cls or "").lower()
            if not any(k in cl for k in ("edit", "richedit", "text")):
                return True
            n = int(_user32.SendMessageW(int(child), WM_GETTEXTLENGTH, 0, 0))
            if n <= 0:
                return True
            n = min(n, max_chars)
            buf = ctypes.create_unicode_buffer(n + 1)
            _user32.SendMessageW(int(child), WM_GETTEXT, n + 1, buf)
            text = (buf.value or "").strip()
            if text:
                out.append(text[:max_chars])
        except Exception:
            pass
        return True

    try:
        _user32.EnumChildWindows(int(hwnd), _WNDENUMPROC(_cb), 0)
    except Exception:
        return out
    return out


def invoke_raw(raw) -> Optional[str]:
    """Invoke through UIA patterns directly. Returns the pattern used, or None."""
    if raw is None:
        return None
    try:
        from pywinauto.uia_defines import IUIA
        dll = IUIA().UIA_dll
    except Exception:
        return None
    attempts = (
        ("invoke", "UIA_InvokePatternId", "IUIAutomationInvokePattern", "Invoke"),
        ("toggle", "UIA_TogglePatternId", "IUIAutomationTogglePattern", "Toggle"),
        ("select", "UIA_SelectionItemPatternId", "IUIAutomationSelectionItemPattern", "Select"),
        ("expand", "UIA_ExpandCollapsePatternId", "IUIAutomationExpandCollapsePattern", "Expand"),
    )
    for label, prop, iface_name, method in attempts:
        try:
            iface = getattr(dll, iface_name)
            pattern = raw.GetCurrentPatternAs(getattr(dll, prop), iface._iid_)
            if not pattern:
                continue
            getattr(pattern, method)()
            return label
        except Exception:
            continue
    try:
        legacy = raw.GetCurrentPatternAs(
            dll.UIA_LegacyIAccessiblePatternId, dll.IUIAutomationLegacyIAccessiblePattern._iid_)
        if legacy:
            legacy.DoDefaultAction()
            return "legacy"
    except Exception:
        pass
    return None


def focus_raw(raw) -> bool:
    try:
        raw.SetFocus()
        return True
    except Exception:
        return False


class UiaTreeCache:
    def __init__(self, ttl: float = 2.5, max_descendants: int = 400):
        self.ttl = ttl
        self.max_descendants = max_descendants
        self._lock = threading.RLock()
        self._desktop = None
        self._trees: Dict[Tuple[int, int], CachedTree] = {}
        self._roots: Dict[Tuple[int, int], Tuple[Any, int, float]] = {}
        self._windows_cache: List[Dict[str, Any]] = []
        self._windows_at = 0.0
        self.stats = {"builds": 0, "hits": 0, "misses": 0, "fast_path": 0, "slow_path": 0}

    # ── legacy pywinauto fallback ────────────────────────────────────

    def _ensure_desktop(self):
        if self._desktop is not None:
            return True
        try:
            _import_pywinauto_quiet()
            from pywinauto import Desktop
            self._desktop = Desktop(backend="uia")
            return True
        except Exception:
            return False

    def invalidate(self, pid: Optional[int] = None, window_id: Optional[int] = None) -> None:
        with self._lock:
            if pid is None:
                self._trees.clear()
                self._roots.clear()
                self._windows_at = 0.0
                return
            dead = [
                k for k in self._trees
                if k[0] == int(pid) and (window_id is None or k[1] == int(window_id or 0))
            ]
            for k in dead:
                self._trees.pop(k, None)
                self._roots.pop(k, None)

    def list_windows(self, force: bool = False) -> List[Dict[str, Any]]:
        with self._lock:
            if not force and self._windows_cache and (time.time() - self._windows_at) < 0.8:
                return list(self._windows_cache)
        out = enum_top_windows(visible_only=True)
        if not out and self._ensure_desktop():
            try:
                for w in self._desktop.windows():
                    try:
                        if not w.is_visible():
                            continue
                        out.append({
                            "title": w.window_text() or "",
                            "handle": int(w.handle),
                            "pid": int(w.process_id()),
                            "class_name": w.class_name(),
                            "visible": True,
                        })
                    except Exception:
                        continue
            except Exception:
                pass
        with self._lock:
            self._windows_cache = out
            self._windows_at = time.time()
        return list(out)

    def main_window_for_pid(self, pid: int) -> Optional[Dict[str, Any]]:
        best = None
        best_area = -1
        for w in self.list_windows():
            if int(w.get("pid") or -1) != int(pid):
                continue
            r = w.get("rect") or [0, 0, 0, 0]
            area = max(0, r[2] - r[0]) * max(0, r[3] - r[1])
            if area > best_area:
                best_area = area
                best = w
        return best

    def _resolve_hwnd(self, pid: int, window_id: Optional[int]) -> Optional[int]:
        if window_id:
            return int(window_id)
        win = self.main_window_for_pid(pid)
        return int(win["handle"]) if win else None

    def _find_root(self, pid: int, window_id: Optional[int]):
        """Cached IUIAutomationElement for the target window."""
        key = (int(pid), int(window_id or 0))
        with self._lock:
            hit = self._roots.get(key)
            if hit and (time.time() - hit[2]) < 5.0:
                return hit[0]
        hwnd = self._resolve_hwnd(pid, window_id)
        if hwnd is None:
            return None
        fast = get_fast_uia()
        root = fast.element_from_handle(hwnd)
        if root is None:
            return None
        with self._lock:
            self._roots[key] = (root, hwnd, time.time())
        return root

    def get_tree(self, pid: int, window_id: Optional[int] = None, force: bool = False) -> CachedTree:
        key = (int(pid), int(window_id or 0))
        with self._lock:
            hit = self._trees.get(key)
            if hit and not force and (time.time() - hit.built_at) < self.ttl:
                self.stats["hits"] += 1
                return hit
            self.stats["misses"] += 1

        t0 = time.time()
        hwnd = self._resolve_hwnd(pid, window_id)
        root = self._find_root(pid, window_id)
        if root is None:
            empty = CachedTree(pid=pid, window_id=window_id, built_at=time.time())
            with self._lock:
                self._trees[key] = empty
            return empty

        title = ""
        try:
            title = _window_title(hwnd) if hwnd else ""
        except Exception:
            pass

        fast = get_fast_uia()
        raws, truncated = fast.descendants(root, self.max_descendants)
        if raws:
            self.stats["fast_path"] += 1
            elements, by_name = self._build_from_raw(fast, raws)
        else:
            self.stats["slow_path"] += 1
            elements, by_name = self._build_legacy(pid, window_id)
            truncated = False

        # Second pass: Win32 edit text when UIA Value/Text is empty (classic Notepad).
        if hwnd and not any(getattr(e, "value", None) for e in elements):
            for blob in win32_child_edit_texts(int(hwnd), max_chars=4000):
                if not blob:
                    continue
                el = CachedElement(
                    index=len(elements),
                    name="",
                    role="edit",
                    bbox=None,
                    value=blob,
                    value_via="win32",
                    raw=None,
                )
                elements.append(el)
                by_name.setdefault(blob.lower()[:120], []).append(el.index)

        self.stats["builds"] += 1
        tree = CachedTree(
            pid=int(pid),
            window_id=hwnd if hwnd else window_id,
            title=title,
            elements=elements,
            by_name=by_name,
            built_at=time.time(),
            root=root,
            ui_hash=_hash_elements(elements),
            build_ms=int((time.time() - t0) * 1000),
            truncated=truncated,
        )
        with self._lock:
            self._trees[key] = tree
        return tree

    def _build_from_raw(self, fast: _FastUia, raws: List[Any]):
        """Collapse duplicates, keeping the most actionable role per region."""
        vl, vt, vr, vb = virtual_screen()
        # bucket key -> CachedElement, so the Button wins over its inner Text
        buckets: Dict[Tuple[Any, ...], CachedElement] = {}
        order: List[Tuple[Any, ...]] = []
        for raw in raws:
            read = fast.read(raw)
            if read is None:
                continue
            name, role, bbox, on_screen, enabled, aid = read
            role_l = (role or "").lower()
            value = ""
            value_via = ""
            # Pull Value/Text for content roles + any interactive edit-like control.
            if role_l in CONTENT_ROLES or role_l in INTERACTIVE_ROLES or not name:
                value, value_via = read_element_value_meta(raw)
            if not name and not value and role_l not in INTERACTIVE_ROLES and role_l not in CONTENT_ROLES:
                continue
            if bbox:
                # Guard against windows parked off the virtual desktop.
                cx, cy = (bbox[0] + bbox[2]) // 2, (bbox[1] + bbox[3]) // 2
                if cx < vl or cx > vr or cy < vt or cy > vb:
                    on_screen = False
            key = (name.lower(), tuple(bbox) if bbox else None, (value[:40].lower() if value else ""))
            existing = buckets.get(key)
            candidate = CachedElement(
                index=-1, name=name, role=str(role), bbox=bbox,
                on_screen=on_screen, enabled=enabled, automation_id=aid,
                value=value, value_via=value_via, raw=raw,
            )
            if existing is None:
                buckets[key] = candidate
                order.append(key)
            elif candidate.rank > existing.rank:
                buckets[key] = candidate
            elif candidate.rank == existing.rank and candidate.value and not existing.value:
                buckets[key] = candidate

        elements: List[CachedElement] = []
        by_name: Dict[str, List[int]] = {}
        for key in order:
            el = buckets[key]
            el.index = len(elements)
            elements.append(el)
            if el.name:
                by_name.setdefault(el.name.lower(), []).append(el.index)
            if el.value and el.value.lower() != (el.name or "").lower():
                by_name.setdefault(el.value.lower()[:120], []).append(el.index)
        return elements, by_name

    def _build_legacy(self, pid: int, window_id: Optional[int]):
        """pywinauto walk, used only when the cached COM path is unavailable."""
        if not self._ensure_desktop():
            return [], {}
        root = None
        try:
            hwnd = self._resolve_hwnd(pid, window_id)
            for w in self._desktop.windows():
                try:
                    if int(w.handle) == int(hwnd):
                        root = w
                        break
                except Exception:
                    continue
        except Exception:
            return [], {}
        if root is None:
            return [], {}
        try:
            desc = list(root.descendants())[: self.max_descendants]
        except Exception:
            return [], {}
        elements: List[CachedElement] = []
        by_name: Dict[str, List[int]] = {}
        seen = set()
        for el in desc:
            try:
                name = (el.window_text() or "").strip()
            except Exception:
                name = ""
            role = ""
            try:
                role = el.element_info.control_type or ""
            except Exception:
                pass
            value = ""
            role_l = str(role).lower()
            if role_l in CONTENT_ROLES:
                try:
                    value = (el.get_value() or "").strip() if hasattr(el, "get_value") else ""
                except Exception:
                    value = ""
                if not value:
                    try:
                        value = (el.iface_value.CurrentValue or "").strip()
                    except Exception:
                        value = ""
            if not name and not value and role_l not in INTERACTIVE_ROLES:
                continue
            bbox = None
            try:
                r = el.rectangle()
                if r.right > r.left and r.bottom > r.top:
                    bbox = [int(r.left), int(r.top), int(r.right), int(r.bottom)]
            except Exception:
                pass
            key = (name.lower(), tuple(bbox) if bbox else None)
            if key in seen:
                continue
            seen.add(key)
            idx = len(elements)
            elements.append(CachedElement(index=idx, name=name, role=str(role),
                                          bbox=bbox, value=value, live=el))
            if name:
                by_name.setdefault(name.lower(), []).append(idx)
            if value:
                by_name.setdefault(value.lower()[:120], []).append(idx)
        return elements, by_name

    def text_corpus(self, pid: int, window_id: Optional[int] = None,
                    force: bool = False, max_chars: int = 4000) -> str:
        """Concatenated name+value text for verify/type honesty checks."""
        tree = self.get_tree(pid, window_id, force=force)
        chunks: List[str] = []
        total = 0
        for el in tree.elements:
            for part in (el.name, el.value):
                if not part:
                    continue
                chunks.append(part)
                total += len(part)
                if total >= max_chars:
                    return "\n".join(chunks)[:max_chars]
        return "\n".join(chunks)

    def get_element(self, pid: int, element_index: int, window_id: Optional[int] = None):
        tree = self.get_tree(pid, window_id)
        if 0 <= element_index < len(tree.elements):
            live = tree.elements[element_index].live
            if live is not None:
                return live
        tree = self.get_tree(pid, window_id, force=True)
        if 0 <= element_index < len(tree.elements):
            return tree.elements[element_index].live
        return None

    def get_cached(self, pid: int, element_index: int,
                   window_id: Optional[int] = None) -> Optional[CachedElement]:
        tree = self.get_tree(pid, window_id)
        if 0 <= element_index < len(tree.elements):
            return tree.elements[element_index]
        return None

    def find_matches(self, pid: int, query: str,
                     window_id: Optional[int] = None) -> List[CachedElement]:
        """Rank by name match, then by how actionable the role is."""
        q = (query or "").strip().lower()
        if not q:
            return []
        tree = self.get_tree(pid, window_id)
        hits = self._rank(tree, q)
        if hits:
            return hits
        # A miss is usually a stale view: the page scrolled and the target was
        # offscreen (so filtered out) when this tree was built. Re-read once
        # before reporting that the element does not exist.
        fresh = self.get_tree(pid, window_id, force=True)
        return self._rank(fresh, q)

    @staticmethod
    def _rank(tree: CachedTree, q: str) -> List[CachedElement]:
        scored: List[Tuple[float, int, CachedElement]] = []
        for el in tree.elements:
            best = 0.0
            for field in (el.name, el.value):
                if not field:
                    continue
                nl = field.lower()
                if nl == q:
                    score = 1.0
                elif nl.startswith(q) or nl.endswith(q):
                    score = 0.86
                elif q in nl:
                    score = 0.78
                elif nl in q:
                    score = 0.7
                else:
                    continue
                # Shorter names that match are more specific.
                score -= min(0.12, abs(len(nl) - len(q)) * 0.004)
                if score > best:
                    best = score
            if best <= 0:
                continue
            if not el.on_screen:
                best -= 0.5
            if not el.enabled:
                best -= 0.15
            scored.append((best, el.rank, el))

        scored.sort(key=lambda s: (round(s[0], 3), s[1]), reverse=True)
        return [s[2] for s in scored]

    def find_by_title_fast(self, pid: int, query: str,
                           window_id: Optional[int] = None) -> Optional[CachedElement]:
        matches = self.find_matches(pid, query, window_id)
        return matches[0] if matches else None


def _hash_elements(elements: List[CachedElement]) -> str:
    """Stable fingerprint of the visible UI, for change verification."""
    h = hashlib.sha1()
    for e in elements:
        val = (e.value or "")[:120]
        h.update(f"{e.name}|{val}|{e.role}|{e.bbox}|{e.enabled}\n".encode("utf-8", "ignore"))
    return h.hexdigest()[:16]


# Process-lifetime singleton
_CACHE: Optional[UiaTreeCache] = None
_CACHE_LOCK = threading.Lock()


def get_uia_cache() -> UiaTreeCache:
    global _CACHE
    with _CACHE_LOCK:
        if _CACHE is None:
            _CACHE = UiaTreeCache()
        return _CACHE
