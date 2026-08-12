"""
Aether Smart Controller v1.5

Everything practical for higher accuracy + speed:
  - Synthetic accessibility/background hands by default
  - Optional legacy Cua compatibility adapter
  - Local OpenCV+OCR grounding
  - Observation cache (continuous perception)
  - UI memory of successful targets
  - smart_click / smart_type with verify + retry
  - smart_scroll / scroll_into_view / hover / smart_drag / smart_hotkey
  - Batched actions (one observe, many acts)
  - Region-aware verification
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, Union

from .perception import PerceptionEngine
from .backends import ActionBackend, CuaBackend, LocalBackend, get_best_backend, DeliveryResult
from .memory import UIMemory
from .safety import SafetyGate, SafetyConfig
from .clipboard import get_clipboard, set_clipboard
from .config import AetherConfig
from .actionlog import ActionLog
from .macros import MacroStore
from .annotate import annotate_to_base64

try:
    from .browser import BrowserEngineSync
    HAS_BROWSER = True
except ImportError:
    HAS_BROWSER = False


@dataclass
class Target:
    kind: str
    label: str
    bbox: Optional[List[int]] = None
    x: Optional[int] = None
    y: Optional[int] = None
    confidence: float = 0.5
    source: str = ""
    pid: Optional[int] = None
    window_id: Optional[int] = None
    element_index: Optional[int] = None
    meta: Dict[str, Any] = field(default_factory=dict)

    @property
    def center(self) -> Optional[Tuple[int, int]]:
        if self.x is not None and self.y is not None:
            return (self.x, self.y)
        if self.bbox and len(self.bbox) == 4:
            x1, y1, x2, y2 = self.bbox
            return ((x1 + x2) // 2, (y1 + y2) // 2)
        return None

    @property
    def is_a11y(self) -> bool:
        return self.kind == "a11y" and self.pid is not None and self.element_index is not None


@dataclass
class ActionOutcome:
    success: bool
    verified: bool
    message: str
    attempts: int = 1
    target: Optional[Target] = None
    pre_obs_id: Optional[str] = None
    post_obs_id: Optional[str] = None
    elapsed: float = 0.0
    backend: str = "local"
    from_memory: bool = False


def _score_match(query: str, text: str, base: float = 0.5) -> float:
    q = query.lower().strip()
    t = (text or "").lower().strip()
    if not q or not t:
        return 0.0
    if q == t:
        return min(1.0, base + 0.4)
    if q in t:
        return min(1.0, base + 0.25)
    if t in q:
        return min(1.0, base + 0.12)
    qt, tt = set(q.split()), set(t.split())
    if qt and tt:
        overlap = len(qt & tt) / max(len(qt), 1)
        if overlap >= 0.5:
            return min(1.0, base + 0.15 * overlap)
    return 0.0


def _parse_cua_tree(state: Dict[str, Any], pid: int, window_id: Optional[int]) -> List[Target]:
    targets: List[Target] = []
    elements = []
    if isinstance(state, dict):
        for key in ("elements", "tree", "nodes", "data", "accessibility"):
            val = state.get(key)
            if isinstance(val, list):
                elements = val
                break
    for i, el in enumerate(elements):
        if not isinstance(el, dict):
            continue
        idx = el.get("element_index", el.get("index", el.get("id", i)))
        try:
            idx = int(idx)
        except Exception:
            idx = i
        name = el.get("name") or el.get("title") or el.get("label") or el.get("value") or el.get("role") or ""
        role = el.get("role") or el.get("type") or ""
        label = f"{name}".strip() or f"{role}".strip() or f"element-{idx}"
        bbox = el.get("bbox") or el.get("bounds") or el.get("frame")
        if isinstance(bbox, dict):
            bbox = [
                int(bbox.get("x", bbox.get("left", 0))),
                int(bbox.get("y", bbox.get("top", 0))),
                int(bbox.get("x", 0) + bbox.get("width", 0)),
                int(bbox.get("y", 0) + bbox.get("height", 0)),
            ]
        actions = el.get("actions") or []
        conf = 0.55
        if any(a in str(actions).lower() for a in ("press", "click", "axpress")):
            conf = 0.7
        if role and any(r in str(role).lower() for r in ("button", "link", "textfield", "checkbox")):
            conf = max(conf, 0.65)
        t = Target(
            kind="a11y", label=label,
            bbox=bbox if isinstance(bbox, list) and len(bbox) == 4 else None,
            confidence=conf, source="cua-a11y",
            pid=pid, window_id=window_id, element_index=idx,
            meta={"role": role, "actions": actions},
        )
        if t.bbox and t.center:
            t.x, t.y = t.center
        targets.append(t)
    return targets


def _env_prefer_cua(default: bool = False) -> bool:
    """Resolve prefer_cua from env / ~/.aether/config.json (Synthetic-first by default)."""
    import os
    env = (os.environ.get("EXO_PREFER_CUA") or os.environ.get("AETHER_PREFER_CUA") or "").strip().lower()
    if env in ("1", "true", "yes", "on"):
        return True
    if env in ("0", "false", "no", "off"):
        return False
    try:
        from exo_control.config import AetherConfig
        return bool(AetherConfig.load().prefer_cua)
    except Exception:
        return default


class SmartController:
    def __init__(
        self,
        prefer_cua: Optional[bool] = None,
        max_retries: int = 3,
        verify: bool = True,
        similarity_threshold: float = 0.97,
        cache_ttl: float = 0.35,
    ):
        if prefer_cua is None:
            prefer_cua = _env_prefer_cua(False)
        # OCR is lazy — never construct easyocr/torch on controller init.
        self.perception = PerceptionEngine(use_ocr=True, ocr_engine="auto")
        self.perception.set_cache_ttl(cache_ttl)
        self.prefer_cua = prefer_cua
        self.backend: ActionBackend = get_best_backend(prefer_cua=prefer_cua, prefer_synthetic=True)
        self.local_fallback = LocalBackend()
        self.max_retries = max_retries
        self.verify = verify
        self.similarity_threshold = similarity_threshold
        self.memory = UIMemory()
        try:
            _cfg = AetherConfig.load()
            _max_a = int(getattr(_cfg, "max_actions_per_minute", 90) or 90)
            _max_c = int(getattr(_cfg, "max_clicks_per_minute", 45) or 45)
        except Exception:
            _max_a, _max_c = 90, 45
        self.safety = SafetyGate(SafetyConfig(
            max_actions_per_minute=_max_a,
            max_clicks_per_minute=_max_c,
        ))
        self._safety_prechecked = False
        self._focus_pid: Optional[int] = None
        self._focus_window_id: Optional[int] = None
        self._focus_rect: Optional[Tuple[int, int, int, int]] = None
        self._focus_monitor: Optional[int] = None
        self._browser = None
        self._metrics = {"clicks": 0, "types": 0, "batches": 0, "memory_hits": 0, "waits": 0, "fills": 0}
        self._timings: Dict[str, Dict[str, Any]] = {}
        self._started_at = time.time()
        self.log = ActionLog(enabled=True)
        self.macros = MacroStore()
        self._eyes = None  # RealtimeEyes, lazy

    @property
    def backend_name(self) -> str:
        return self.backend.name

    def _uia(self):
        from .uia_cache import get_uia_cache
        return get_uia_cache()

    def _get_eyes(self):
        if getattr(self, "_eyes", None) is None:
            from .realtime import get_realtime_eyes
            self._eyes = get_realtime_eyes(getattr(self, "perception", None))
        return self._eyes

    def eyes_start(self, fps: float = 6.0, ocr_on_change: bool = False) -> Dict[str, Any]:
        eyes = self._get_eyes()
        eyes.fps = max(1.0, float(fps))
        eyes.ocr_on_change = bool(ocr_on_change)
        return eyes.start()

    def eyes_stop(self) -> Dict[str, Any]:
        return self._get_eyes().stop()

    def eyes_read(self, force_ocr: bool = False) -> Dict[str, Any]:
        """Realtime read of what you're looking at (focused window + a11y + OCR)."""
        return self._get_eyes().read_now(force_ocr=force_ocr)

    def glance(self, force_ocr: bool = False) -> Dict[str, Any]:
        """Compact what a person would notice after moving the mouse or keys."""
        raw = self.eyes_read(force_ocr=force_ocr)
        if not isinstance(raw, dict) or not raw.get("ok"):
            err = raw.get("error") if isinstance(raw, dict) else "no eyes"
            return {"ok": False, "error": err}
        labels: List[str] = []
        for item in raw.get("a11y") or []:
            if isinstance(item, dict) and item.get("name"):
                labels.append(str(item["name"])[:80])
            if len(labels) >= 12:
                break
        if not labels:
            for item in raw.get("labels") or []:
                if isinstance(item, dict) and item.get("text"):
                    labels.append(str(item["text"])[:80])
                if len(labels) >= 8:
                    break
        return {
            "ok": True,
            "title": raw.get("title") or "",
            "changed": bool(raw.get("changed")),
            "age_ms": raw.get("age_ms"),
            "phash": str(raw.get("phash") or "")[:16],
            "labels": labels,
            "pid": raw.get("pid"),
        }

    def read_ui(self, pid: Optional[int] = None, force: bool = False,
                interactive_only: bool = False, max_elements: int = 120) -> Dict[str, Any]:
        """Fast a11y dump of focused/target window — no OCR, no screenshot."""
        t0 = time.time()
        pid = pid or self._focus_pid
        if pid is None:
            # Infer from foreground
            try:
                import ctypes
                from ctypes import wintypes
                hwnd = ctypes.windll.user32.GetForegroundWindow()
                dp = wintypes.DWORD()
                ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(dp))
                pid = int(dp.value)
                self._focus_pid = pid
                self._focus_window_id = int(hwnd)
            except Exception:
                return {"ok": False, "error": "no focus pid"}
        tree = self._uia().get_tree(int(pid), self._focus_window_id, force=force)
        from .uia_cache import INTERACTIVE_ROLES

        chosen = tree.elements
        if interactive_only:
            chosen = [e for e in chosen if (e.role or "").lower() in INTERACTIVE_ROLES]
        labels: List[str] = []
        values: List[str] = []
        value_entries: List[Dict[str, Any]] = []
        for e in chosen:
            if e.name and e.name not in labels:
                labels.append(e.name)
            val = (getattr(e, "value", None) or "").strip()
            if val and val not in values:
                clipped = val if len(val) <= 240 else val[:237] + "..."
                values.append(clipped)
                value_entries.append({
                    "text": clipped,
                    "via": getattr(e, "value_via", None) or "uia",
                    "role": e.role,
                    "element_index": e.index,
                })
        offscreen = sum(1 for e in tree.elements if not e.on_screen)
        self._record_stat("read_ui", time.time() - t0)
        return {
            "ok": True,
            "pid": tree.pid,
            "window_id": tree.window_id,
            "title": tree.title,
            "age_ms": int((time.time() - tree.built_at) * 1000),
            "ui_hash": tree.ui_hash,
            "labels": labels[:max_elements],
            "values": values[:max_elements],
            "value_entries": value_entries[:max_elements],
            "elements": [e.as_dict() for e in chosen[:max_elements]],
            "element_count": len(tree.elements),
            "interactive_count": sum(
                1 for e in tree.elements if (e.role or "").lower() in INTERACTIVE_ROLES),
            "offscreen_count": offscreen,
            "truncated": tree.truncated or len(chosen) > max_elements,
            "build_ms": tree.build_ms,
            "elapsed": round(time.time() - t0, 3),
        }

    def ui_hash(self, force: bool = False) -> str:
        """Cheap fingerprint of the focused window's a11y state."""
        if self._focus_pid is None:
            return ""
        try:
            return self._uia().get_tree(self._focus_pid, self._focus_window_id,
                                        force=force).ui_hash
        except Exception:
            return ""

    def _record_stat(self, op: str, elapsed: float, ok: bool = True) -> None:
        bucket = self._timings.setdefault(op, {"n": 0, "fail": 0, "ms": []})
        bucket["n"] += 1
        if not ok:
            bucket["fail"] += 1
        samples = bucket["ms"]
        samples.append(round(elapsed * 1000, 1))
        if len(samples) > 200:
            del samples[: len(samples) - 200]

    def exo_attach(self) -> Dict[str, Any]:
        """Discover Exo/WebView2/Chrome CDP and connect browser engine if possible."""
        from .exo_bridge import attach_best
        try:
            eng = self._get_browser()
        except Exception:
            eng = None
        return attach_best(eng)

    def _raise_hwnd(self, hwnd: int) -> bool:
        """Actually take the foreground.

        A bare SetForegroundWindow from a background process is refused by the
        foreground lock, which is why raises kept reporting false and later
        reads targeted a minimized window at negative coordinates. Attaching to
        the current foreground thread lifts that restriction; the result is
        confirmed against GetForegroundWindow rather than trusted.
        """
        try:
            import ctypes
            from ctypes import wintypes
            user32 = ctypes.windll.user32
            hwnd = int(hwnd)
            SW_RESTORE = 9
            if user32.IsIconic(hwnd):
                user32.ShowWindow(hwnd, SW_RESTORE)
            try:
                user32.AllowSetForegroundWindow(-1)
            except Exception:
                pass

            fg = user32.GetForegroundWindow()
            if fg == hwnd:
                return True
            cur_thread = ctypes.windll.kernel32.GetCurrentThreadId()
            fg_thread = user32.GetWindowThreadProcessId(fg, None) if fg else 0
            attached = False
            if fg_thread and fg_thread != cur_thread:
                attached = bool(user32.AttachThreadInput(fg_thread, cur_thread, True))
            try:
                user32.BringWindowToTop(hwnd)
                user32.SetForegroundWindow(hwnd)
                user32.SetActiveWindow(hwnd)
            finally:
                if attached:
                    user32.AttachThreadInput(fg_thread, cur_thread, False)

            deadline = time.time() + 0.6
            while time.time() < deadline:
                if user32.GetForegroundWindow() == hwnd:
                    return True
                time.sleep(0.03)
            return False
        except Exception:
            return False

    def window_state(self, hwnd: Optional[int]) -> Dict[str, Any]:
        """Live geometry/visibility for a window — the ground truth for clicks."""
        if not hwnd:
            return {"known": False}
        try:
            import ctypes
            from ctypes import wintypes
            user32 = ctypes.windll.user32
            rect = wintypes.RECT()
            user32.GetWindowRect(int(hwnd), ctypes.byref(rect))
            from .uia_cache import virtual_screen
            vl, vt, vr, vb = virtual_screen()
            cx = (rect.left + rect.right) // 2
            cy = (rect.top + rect.bottom) // 2
            return {
                "known": True,
                "rect": [int(rect.left), int(rect.top), int(rect.right), int(rect.bottom)],
                "visible": bool(user32.IsWindowVisible(int(hwnd))),
                "minimized": bool(user32.IsIconic(int(hwnd))),
                "foreground": user32.GetForegroundWindow() == int(hwnd),
                "on_screen": vl <= cx <= vr and vt <= cy <= vb,
            }
        except Exception:
            return {"known": False}

    def _hwnd_for_window_op(self, hwnd: Optional[int] = None) -> Optional[int]:
        h = self._focus_window_id if hwnd is None else hwnd
        try:
            return int(h) if h is not None else None
        except Exception:
            return None

    def _window_show(self, action: str, hwnd: Optional[int] = None, cmd: Optional[int] = None) -> Dict[str, Any]:
        """Minimize / maximize / restore / close the focused (or given) HWND."""
        h = self._hwnd_for_window_op(hwnd)
        if h is None:
            return {"ok": False, "error": "no focused window"}
        try:
            import ctypes
            user32 = ctypes.windll.user32
            if action == "close":
                user32.PostMessageW(h, 0x0010, 0, 0)  # WM_CLOSE
            else:
                if cmd is None:
                    return {"ok": False, "error": f"missing ShowWindow cmd for {action}"}
                user32.ShowWindow(h, int(cmd))
            return {
                "ok": True,
                "action": action,
                "window_id": h,
                "window": self.window_state(h),
            }
        except Exception as exc:
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    def window_min(self, hwnd: Optional[int] = None) -> Dict[str, Any]:
        return self._window_show("min", hwnd=hwnd, cmd=6)  # SW_MINIMIZE

    def window_max(self, hwnd: Optional[int] = None) -> Dict[str, Any]:
        return self._window_show("max", hwnd=hwnd, cmd=3)  # SW_MAXIMIZE

    def window_restore(self, hwnd: Optional[int] = None) -> Dict[str, Any]:
        return self._window_show("restore", hwnd=hwnd, cmd=9)  # SW_RESTORE

    def _window_alive(self, hwnd: Optional[int]) -> bool:
        if hwnd is None:
            return False
        try:
            import ctypes
            return bool(ctypes.windll.user32.IsWindow(int(hwnd)))
        except Exception:
            return False

    def _find_discard_button(self) -> Optional[Target]:
        """Locate Don't save / Discard / No on the focused save prompt."""
        # Prefer explicit discard phrasing; bare "No" only if a save prompt is up.
        primary = ("don't save", "dont save", "do not save", "discard")
        secondary = ("no",)
        for needle in primary:
            hit = self._find_visible_label(needle)
            if hit is not None:
                return hit
        # Only accept "No" when UI also mentions save/unsaved.
        try:
            corpus = ""
            if self._focus_pid is not None:
                corpus = self._uia().text_corpus(
                    int(self._focus_pid), self._focus_window_id, force=True, max_chars=2000
                ).lower()
            title = ""
            tree = self._uia().get_tree(self._focus_pid, self._focus_window_id, force=False) if self._focus_pid else None
            if tree is not None:
                title = (tree.title or "").lower()
            if any(k in corpus or k in title for k in ("save", "unsaved", "want to save")):
                for needle in secondary:
                    hit = self._find_visible_label(needle)
                    if hit is not None:
                        return hit
        except Exception:
            pass
        return None

    def _dismiss_unsaved_prompt(self, closed_hwnd: Optional[int], timeout: float = 2.5) -> Dict[str, Any]:
        """If a Save/Don't-save dialog appears after close, pick Don't save.

        Agents type into Notepad then close — without this, WM_CLOSE leaves a
        modal that blocks the desktop (and must not press Save).
        """
        deadline = time.time() + max(0.4, float(timeout))
        attempts: List[str] = []
        while time.time() < deadline:
            # Original window already gone and no prompt → done.
            if closed_hwnd is not None and not self._window_alive(closed_hwnd):
                # Check briefly for a lingering dialog from same app.
                pass

            # Click Don't save if present on focused tree.
            hit = self._find_discard_button()
            if hit is not None:
                delivery = self._deliver_click(target=hit, button="left")
                attempts.append(f"click:{hit.label}")
                if delivery.ok:
                    time.sleep(0.2)
                    gone = closed_hwnd is None or not self._window_alive(closed_hwnd)
                    return {
                        "ok": True,
                        "dismissed": True,
                        "via": "click",
                        "label": hit.label,
                        "gone": gone,
                        "attempts": attempts,
                    }

            # Scan top-level windows for a Notepad/save dialog and focus it.
            try:
                for w in self._uia().list_windows(force=True)[:30]:
                    title = (w.get("title") or "")
                    tl = title.lower()
                    if not w.get("visible"):
                        continue
                    if not any(k in tl for k in ("notepad", "save", "unsaved")):
                        continue
                    try:
                        self.smart_focus(title=title, pid=int(w.get("pid") or 0) or None)
                    except Exception:
                        continue
                    hit = self._find_discard_button()
                    if hit is not None:
                        delivery = self._deliver_click(target=hit, button="left")
                        attempts.append(f"focus+click:{hit.label}")
                        if delivery.ok:
                            time.sleep(0.2)
                            gone = closed_hwnd is None or not self._window_alive(closed_hwnd)
                            return {
                                "ok": True,
                                "dismissed": True,
                                "via": "focus+click",
                                "label": hit.label,
                                "dialog": title,
                                "gone": gone,
                                "attempts": attempts,
                            }
            except Exception as exc:
                attempts.append(f"scan_err:{exc}")

            # Hotkeys only if a save-ish dialog is focused (avoid typing "n" into apps).
            try:
                title = ""
                if self._focus_pid is not None:
                    tr = self._uia().get_tree(self._focus_pid, self._focus_window_id, force=False)
                    title = (tr.title or "").lower()
                if any(k in title for k in ("notepad", "save", "unsaved")) or self._find_discard_button():
                    for keys in (["alt", "n"], ["n"]):
                        self.smart_hotkey(keys)
                        attempts.append(f"hotkey:{'+'.join(keys)}")
                        time.sleep(0.2)
                        if closed_hwnd is not None and not self._window_alive(closed_hwnd):
                            return {
                                "ok": True,
                                "dismissed": True,
                                "via": "hotkey",
                                "keys": keys,
                                "gone": True,
                                "attempts": attempts,
                            }
            except Exception as exc:
                attempts.append(f"hotkey_err:{exc}")

            time.sleep(0.12)

        gone = closed_hwnd is None or not self._window_alive(closed_hwnd)
        return {
            "ok": gone,
            "dismissed": False,
            "gone": gone,
            "attempts": attempts,
            "error": None if gone else "save prompt not dismissed",
        }

    def window_close(
        self,
        hwnd: Optional[int] = None,
        discard_unsaved: bool = True,
        wait_gone: float = 2.5,
    ) -> Dict[str, Any]:
        """Close focused/given window; press Don't save on unsaved prompts (default)."""
        h = self._hwnd_for_window_op(hwnd)
        out = self._window_show("close", hwnd=hwnd)
        if not out.get("ok"):
            return out
        if not discard_unsaved:
            out["gone"] = not self._window_alive(h)
            return out
        time.sleep(0.2)
        if h is not None and not self._window_alive(h):
            out["gone"] = True
            out["discard"] = {"ok": True, "dismissed": False, "reason": "already_gone", "gone": True}
            return out
        discard = self._dismiss_unsaved_prompt(closed_hwnd=h, timeout=wait_gone)
        out["discard"] = discard
        out["gone"] = bool(discard.get("gone")) or not self._window_alive(h)
        if not out["gone"] and not discard.get("dismissed"):
            out["warning"] = "window may still be open (save dialog?)"
        # Drop window list cache so a following `windows` op is not stale.
        try:
            self._uia().invalidate()
        except Exception:
            pass
        return out

    def _get_browser(self):
        if not HAS_BROWSER:
            return None
        if self._browser is None:
            self._browser = BrowserEngineSync(headless=False)
            self._browser.start()
        return self._browser

    # ── Eyes ────────────────────────────────────────────────────────

    def observe(self, use_cache: bool = False, **kwargs) -> Dict[str, Any]:
        mon = kwargs.get("monitor")
        if mon is None and self._focus_monitor is not None:
            kwargs = dict(kwargs)
            kwargs["monitor"] = int(self._focus_monitor)
        out = (self.perception.observe_cached(**kwargs) if use_cache
               else self.perception.observe(**kwargs))
        # PerceptionEngine reports a11y as unwired; it is wired here via UIA.
        try:
            if isinstance(out, dict) and self._focus_pid is not None:
                tree = self._uia().get_tree(self._focus_pid, self._focus_window_id)
                out["a11y"] = {
                    "available": True,
                    "source": "uia",
                    "title": tree.title,
                    "ui_hash": tree.ui_hash,
                    "tree": [e.as_dict() for e in tree.elements[:120]],
                    "count": len(tree.elements),
                }
        except Exception:
            pass
        if isinstance(out, dict) and kwargs.get("monitor") is not None:
            out["monitor"] = int(kwargs["monitor"])
        return out

    def list_windows(
        self,
        monitor: Optional[int] = None,
        *,
        as_dict: bool = False,
    ):
        """List top-level windows.

        Historical callers get a bare list. Prefer ``as_dict=True`` / exec op
        ``windows`` which always returns ``{ok, windows, count}``.
        """
        try:
            windows = self._uia().list_windows()
        except Exception:
            windows = self.backend.list_windows()
        windows = list(windows or [])
        if monitor is not None:
            from .monitors import filter_windows_for_monitor
            hits, mon = filter_windows_for_monitor(windows, int(monitor))
            windows = hits if mon is not None else []
        if as_dict:
            out: Dict[str, Any] = {"ok": True, "windows": windows, "count": len(windows)}
            if monitor is not None:
                out["monitor"] = int(monitor)
            return out
        return windows

    def _focus_process_name(self) -> Optional[str]:
        pid = self._focus_pid
        if pid is None:
            return None
        try:
            import psutil  # type: ignore
            from pathlib import Path as _P
            return _P(psutil.Process(int(pid)).name()).stem.lower()
        except Exception:
            return None

    def focus_window(self, pid: "int | str", window_id: Optional[int] = None) -> Dict[str, Any]:
        # Convenience: title substring is accepted as well as pid.
        if isinstance(pid, str):
            return self.smart_focus(title=pid)
        self._focus_pid = pid
        self._focus_window_id = window_id
        try:
            self._get_eyes().set_focus_hint(pid, window_id, monitor=self._focus_monitor)
        except Exception:
            pass
        if window_id is None:
            win = self._uia().main_window_for_pid(int(pid))
            if win:
                window_id = int(win["handle"])
                self._focus_window_id = window_id
        raised = False
        if window_id is not None:
            raised = self._raise_hwnd(int(window_id))
        # A stale tree from before the raise would describe the old window.
        self._uia().invalidate(pid, window_id)
        # Warm UIA cache off the hot path so focus returns immediately
        import threading
        def _warm():
            try:
                self._uia().get_tree(pid, window_id)
            except Exception:
                pass
        threading.Thread(target=_warm, name="aether-uia-warm", daemon=True).start()
        return {"ok": True, "pid": pid, "window_id": window_id, "raised": raised,
                "window": self.window_state(window_id)}

    def find_targets(
        self,
        query: str,
        obs: Optional[Dict] = None,
        min_confidence: float = 0.3,
        use_cua_a11y: bool = True,
        use_memory: bool = True,
        allow_ocr: bool = True,
    ) -> List[Target]:
        targets: List[Target] = []

        # Memory boost (process-name key survives PID recycle across relaunch)
        if use_memory:
            hit = self.memory.lookup(
                query,
                self._focus_pid,
                process_name=self._focus_process_name(),
            )
            if hit:
                self._metrics["memory_hits"] += 1
                targets.append(Target(
                    kind=hit.kind or "memory",
                    label=hit.label,
                    bbox=hit.bbox,
                    x=hit.x, y=hit.y,
                    confidence=min(0.92, 0.55 + hit.score * 0.4),
                    source="memory",
                    pid=hit.pid or self._focus_pid,
                    window_id=hit.window_id or self._focus_window_id,
                    element_index=hit.element_index,
                    meta={"process_name": hit.process_name},
                ))

        # Fast path: shared UIA cache (avoids cold Desktop walks)
        if use_cua_a11y and self._focus_pid is not None:
            try:
                from .uia_cache import INTERACTIVE_ROLES
                q_norm = (query or "").strip().lower()
                for el in self._uia().find_matches(self._focus_pid, query, self._focus_window_id):
                    name_l = (el.name or "").strip().lower()
                    # An exact name must beat a label that merely contains it,
                    # even after role bonuses, or "Pin X" ties with "X".
                    exact = name_l == q_norm
                    if exact:
                        score = 1.0
                    elif name_l.startswith(q_norm) or name_l.endswith(q_norm):
                        score = 0.72
                    elif q_norm in name_l or name_l in q_norm:
                        score = 0.64
                    else:
                        score = min(0.6, _score_match(query, el.name or query, base=0.5))
                    role_l = (el.role or "").lower()
                    # Name similarity alone ranks a section heading above the
                    # button it labels. Weight by how actionable the role is so
                    # clicks land on controls, not on captions.
                    if role_l in INTERACTIVE_ROLES:
                        score += 0.12
                    elif role_l in ("text", "pane", "group", "document", "image", "list"):
                        score -= 0.15
                    if not el.on_screen:
                        score -= 0.6
                    if not el.enabled:
                        score -= 0.1
                    # Only a true exact match may reach 1.0.
                    score = max(0.0, min(1.0 if exact else 0.92, score))
                    if score < min_confidence:
                        continue
                    # index -1 = direct title hit with live wrapper (no full tree)
                    idx = el.index if el.index is not None and el.index >= 0 else None
                    t = Target(
                        kind="a11y",
                        label=el.name or query,
                        bbox=el.bbox,
                        confidence=score,
                        source="uia-cache" if idx is not None else "uia-title",
                        pid=self._focus_pid,
                        window_id=self._focus_window_id,
                        element_index=idx if idx is not None else -1,
                        meta={"role": el.role, "cached": el, "on_screen": el.on_screen,
                              "enabled": el.enabled},
                    )
                    if t.bbox and t.center:
                        t.x, t.y = t.center
                    targets.append(t)
            except Exception:
                pass

        if use_cua_a11y and self._focus_pid is not None and hasattr(self.backend, "get_window_state") and not targets:
            try:
                state = self.backend.get_window_state(self._focus_pid, self._focus_window_id)
                for t in _parse_cua_tree(state, self._focus_pid, self._focus_window_id):
                    t.source = f"{self.backend.name}-a11y"
                    t.kind = "a11y"
                    score = _score_match(query, t.label, base=t.confidence)
                    if score >= min_confidence:
                        t.confidence = score
                        targets.append(t)
            except Exception:
                pass

        # Fast path: strong a11y/memory hit — skip expensive OCR desktop scan.
        a11y_best = max((t.confidence for t in targets if t.is_a11y or t.source == "memory"), default=0.0)
        if a11y_best >= 0.85 and allow_ocr:
            allow_ocr = False

        if allow_ocr:
            if obs is None:
                obs = self.observe(modes=["ocr", "vision"], include_image=False, use_cache=True)

            for item in obs.get("vision", {}).get("ocr", []):
                text = (item.get("text") or "").strip()
                conf = float(item.get("confidence", 0.5))
                score = _score_match(query, text, base=conf)
                if score < min_confidence:
                    continue
                bbox = item.get("bbox")
                t = Target(kind="ocr", label=text, bbox=bbox, confidence=score, source="ocr", meta=item)
                if t.center:
                    t.x, t.y = t.center
                targets.append(t)

            for el in obs.get("vision", {}).get("elements", []):
                label = (el.get("label") or "").strip()
                conf = float(el.get("confidence", 0.5))
                source = el.get("source") or "vision"
                if source == "fused":
                    conf = min(1.0, conf + 0.05)
                score = _score_match(query, label, base=conf)
                if score < min_confidence:
                    continue
                if label in ("button", "input", "icon", "region") and query.strip():
                    if query.lower() not in label and label not in query.lower():
                        continue
                bbox = el.get("bbox")
                t = Target(kind="element", label=label, bbox=bbox, confidence=score, source=source, meta=el)
                if t.center:
                    t.x, t.y = t.center
                targets.append(t)

        targets.sort(key=lambda t: (t.confidence + (0.1 if t.is_a11y else 0) + (0.06 if t.source == "memory" else 0)), reverse=True)
        # de-dupe by approximate center
        seen = set()
        uniq = []
        for t in targets:
            c = t.center or (-1, -1)
            key = (c[0] // 8, c[1] // 8, (t.label or "")[:24])
            if key in seen:
                continue
            seen.add(key)
            uniq.append(t)
        return uniq

    # ── Delivery ────────────────────────────────────────────────────

    def _invoke_live(self, live, button: str = "left") -> DeliveryResult:
        if live is None:
            return DeliveryResult(False, self.backend.name, "no live element")
        for method in ("invoke", "toggle", "select", "click", "click_input"):
            fn = getattr(live, method, None)
            if not callable(fn):
                continue
            try:
                fn()
                return DeliveryResult(True, self.backend.name, f"live:{method}")
            except Exception:
                continue
        # coord fallback from rectangle
        try:
            r = live.rectangle()
            cx, cy = (int(r.left) + int(r.right)) // 2, (int(r.top) + int(r.bottom)) // 2
            return self.backend.click(x=cx, y=cy, button=button)
        except Exception as e:
            return DeliveryResult(False, self.backend.name, str(e))

    def _deliver_click(self, target: Optional[Target] = None, x: Optional[int] = None,
                       y: Optional[int] = None, button: str = "left") -> DeliveryResult:
        if target and target.is_a11y:
            meta = target.meta or {}
            cached = meta.get("cached")
            if cached is not None and button == "left":
                # Invoke straight through the UIA pattern — no wrapper build,
                # no cursor movement, works on a background window.
                try:
                    from .uia_cache import invoke_raw
                    used = invoke_raw(getattr(cached, "raw", None))
                    if used:
                        return DeliveryResult(True, self.backend.name, f"uia:{used}")
                except Exception:
                    pass
            live = meta.get("live")
            if live is None and cached is not None:
                try:
                    live = cached.live
                except Exception:
                    live = None
            if live is not None and (target.element_index is None or target.element_index < 0):
                res = self._invoke_live(live, button=button)
                if res.ok:
                    return res
            if target.element_index is not None and target.element_index >= 0 and hasattr(self.backend, "click"):
                res = self.backend.click(pid=target.pid, window_id=target.window_id,
                                         element_index=target.element_index, button=button)
                if res.ok:
                    return res
                # Retry via stashed live wrapper
                if live is not None:
                    res = self._invoke_live(live, button=button)
                    if res.ok:
                        return res
        cx, cy = x, y
        if target and target.center:
            cx, cy = target.center
        if cx is None or cy is None:
            return DeliveryResult(False, self.backend.name, "no coordinates")
        # A minimized or parked window reports coordinates like (-30861,-31528).
        # Clicking there hits nothing but still looks like success, so refuse.
        try:
            from .uia_cache import virtual_screen
            vl, vt, vr, vb = virtual_screen()
            if not (vl <= int(cx) <= vr and vt <= int(cy) <= vb):
                return DeliveryResult(
                    False, self.backend.name,
                    f"target offscreen at ({cx},{cy}); window is hidden or minimized")
        except Exception:
            pass
        res = self.backend.click(
            x=int(cx), y=int(cy), button=button,
            pid=getattr(target, "pid", None) if target else self._focus_pid,
            window_id=getattr(target, "window_id", None) if target else self._focus_window_id,
        )
        if res.ok:
            return res
        if self.backend.name != "local":
            return self.local_fallback.click(x=int(cx), y=int(cy), button=button)
        return res

    def _deliver_type(self, text: str, clear: bool = False, target: Optional[Target] = None) -> DeliveryResult:
        kwargs: Dict[str, Any] = {"clear": clear}
        if target and target.is_a11y:
            kwargs.update(pid=target.pid, window_id=target.window_id, element_index=target.element_index)
        elif self._focus_pid is not None:
            kwargs.update(pid=self._focus_pid, window_id=self._focus_window_id)
        res = self.backend.type_text(text, **kwargs)
        if res.ok:
            return res
        if self.backend.name != "local":
            return self.local_fallback.type_text(text, clear=clear)
        return res

    def _verify_change(self, pre: Dict, post: Dict) -> bool:
        diff = post.get("diff") or {}
        if not diff or diff.get("available") is False:
            return True
        sim = diff.get("similarity")
        if sim is None:
            return True
        return float(sim) < self.similarity_threshold

    # ── Smart actions ───────────────────────────────────────────────

    def smart_click(self, query: Optional[str] = None, x: Optional[int] = None,
                    y: Optional[int] = None, button: str = "left",
                    require_change: bool = False,
                    element_index: Optional[int] = None,
                    pid: Optional[int] = None,
                    window_id: Optional[int] = None,
                    label: Optional[str] = None) -> ActionOutcome:
        t0 = time.time()
        if not getattr(self, "_safety_prechecked", False):
            ok_s, why = self.safety.check("click", text=query or "", confirm=False)
            if not ok_s:
                return ActionOutcome(False, False, why, elapsed=0.0, backend=self.backend_name)
        self._metrics["clicks"] += 1

        # Fast path: a11y/memory first — skip desktop OCR/diff (was ~6–9s per click).
        targets: List[Target] = []
        pre: Dict[str, Any] = {}
        pre_id = None
        # Stable script ref → element_index (same exec batch as prior read/observe).
        if element_index is not None:
            use_pid = int(pid) if pid is not None else self._focus_pid
            use_hwnd = int(window_id) if window_id is not None else self._focus_window_id
            if use_pid is None:
                return ActionOutcome(False, False, "ref click needs focus pid",
                                     elapsed=0.0, backend=self.backend_name)
            t = Target(
                kind="a11y",
                label=str(label or query or f"#{element_index}"),
                confidence=0.99,
                source="ref",
                pid=int(use_pid),
                window_id=use_hwnd,
                element_index=int(element_index),
                meta={"role": "?", "via": "ref"},
            )
            try:
                cached = self._uia().get_cached(int(use_pid), int(element_index), use_hwnd)
                if cached is not None:
                    t.label = cached.name or t.label
                    t.bbox = cached.bbox
                    t.meta["role"] = cached.role
                    if t.bbox and t.center:
                        t.x, t.y = t.center
            except Exception:
                pass
            targets = [t]
        if query and not targets:
            targets = self.find_targets(query, obs=None, allow_ocr=False)
            if not targets or targets[0].confidence < 0.85:
                pre = self.observe(modes=["ocr", "vision", "diff"], include_image=False, use_cache=True)
                pre_id = pre.get("obs_id")
                targets = self.find_targets(query, obs=pre, allow_ocr=True)
        if x is not None and y is not None:
            targets.append(Target(kind="coords", label=f"({x},{y})", x=x, y=y, confidence=0.55, source="coords"))
        if not targets:
            if query:
                self.memory.record_failure(
                    query, self._focus_pid, process_name=self._focus_process_name()
                )
            return ActionOutcome(False, False, f"No targets for {query!r}",
                                 elapsed=time.time()-t0, backend=self.backend_name)

        # Retrying down the ranked list can hit a neighbour that merely contains
        # the query — clicking "League of Legends" fell through to "Unpin League
        # of Legends" on the same card. Only retry near-equal matches.
        if query and targets:
            best = targets[0].confidence
            targets = [t for t in targets if t.confidence >= best - 0.08]

        last_msg = ""
        used_memory = False
        for attempt, target in enumerate(targets[: self.max_retries + 1], start=1):
            if target.source == "memory":
                used_memory = True
            pre_hash = self.ui_hash() if (require_change and target.is_a11y) else ""
            delivery = self._deliver_click(target=target, button=button)
            # a11y invoke is authoritative — skip expensive verify unless required.
            if delivery.ok and target.is_a11y and not require_change:
                if query:
                    if not isinstance(target.meta, dict):
                        target.meta = {}
                    target.meta.setdefault("process_name", self._focus_process_name())
                    self.memory.record_success(query, target)
                self.log.record("click", query=query, label=target.label, backend=delivery.backend, success=True)
                if self.macros.is_recording():
                    self.macros.add("click", query=query)
                self._record_stat("smart_click", time.time() - t0)
                return ActionOutcome(
                    True, True,
                    f"Clicked '{target.label}' [{(target.meta or {}).get('role') or '?'}] "
                    f"via {delivery.message} conf={target.confidence:.2f}",
                    attempts=attempt, target=target, pre_obs_id=pre_id, post_obs_id=None,
                    elapsed=time.time()-t0, backend=delivery.backend,
                    from_memory=(target.source == "memory"),
                )
            if delivery.ok and target.is_a11y and require_change:
                # Compare the a11y fingerprint instead of screen pixels: it is
                # ~50x cheaper and does not report success for cosmetic redraws.
                changed = False
                deadline = time.time() + 1.6
                while time.time() < deadline:
                    time.sleep(0.1)
                    if self.ui_hash(force=True) != pre_hash:
                        changed = True
                        break
                if changed:
                    if query:
                        if not isinstance(target.meta, dict):
                            target.meta = {}
                        target.meta.setdefault("process_name", self._focus_process_name())
                        self.memory.record_success(query, target)
                    self.log.record("click", query=query, label=target.label,
                                    backend=delivery.backend, success=True)
                    self._record_stat("smart_click", time.time() - t0)
                    return ActionOutcome(
                        True, True,
                        f"Clicked '{target.label}' and UI changed (conf={target.confidence:.2f})",
                        attempts=attempt, target=target, pre_obs_id=pre_id,
                        elapsed=time.time()-t0, backend=delivery.backend,
                        from_memory=(target.source == "memory"),
                    )
                last_msg = (f"Attempt {attempt} '{target.label}' delivered but UI did not "
                            f"change (hash {pre_hash})")
                continue
            time.sleep(0.12)
            post = self.observe(modes=["diff"], include_image=False, use_cache=False)
            post_id = post.get("obs_id")
            changed = self._verify_change(pre, post) if (self.verify and pre) else True
            if delivery.ok and (not self.verify or changed or not require_change):
                if query:
                    if not isinstance(target.meta, dict):
                        target.meta = {}
                    target.meta.setdefault("process_name", self._focus_process_name())
                    self.memory.record_success(query, target)
                self.log.record("click", query=query, label=target.label, backend=delivery.backend, success=True)
                if self.macros.is_recording():
                    self.macros.add("click", query=query)
                how = f"a11y#{target.element_index}" if target.is_a11y else f"({target.x},{target.y})"
                return ActionOutcome(
                    True, bool(changed),
                    f"Clicked '{target.label}' via {how} conf={target.confidence:.2f}",
                    attempts=attempt, target=target, pre_obs_id=pre_id, post_obs_id=post_id,
                    elapsed=time.time()-t0, backend=delivery.backend,
                    from_memory=(target.source == "memory"),
                )
            last_msg = f"Attempt {attempt} '{target.label}' ok={delivery.ok} changed={changed}"
            pre = post
        if query:
            proc = self._focus_process_name()
            self.memory.record_failure(query, self._focus_pid, process_name=proc)
            # Invalidate-on-miss: memory hits that failed must not stick across relaunch.
            if used_memory:
                self.memory.invalidate(query)
        self._record_stat("smart_click", time.time() - t0, ok=False)
        return ActionOutcome(False, False, last_msg or "all attempts failed",
                             attempts=min(len(targets), self.max_retries+1),
                             pre_obs_id=pre_id, elapsed=time.time()-t0, backend=self.backend_name)

    def _text_in_focus_meta(self, text: str) -> Dict[str, Any]:
        """Locate typed content; prefer UIA/Win32, clipboard only as last resort.

        Returns ``{found: bool, via: str}`` where via is one of
        name|value|text|legacy|win32|clipboard|"".
        """
        needle = (text or "").strip()
        if not needle:
            return {"found": True, "via": "empty"}
        sample = needle if len(needle) <= 120 else needle[:120]
        sample_l = sample.lower()
        if self._focus_pid is None:
            return {"found": False, "via": ""}
        try:
            tree = self._uia().get_tree(
                int(self._focus_pid), self._focus_window_id, force=True
            )
            for el in tree.elements:
                name = (el.name or "")
                val = getattr(el, "value", "") or ""
                if name and sample_l in name.lower():
                    return {"found": True, "via": "name"}
                if val and sample_l in val.lower():
                    return {"found": True, "via": getattr(el, "value_via", None) or "value"}
            corpus = self._uia().text_corpus(
                int(self._focus_pid), self._focus_window_id, force=False, max_chars=6000
            )
            if sample_l in (corpus or "").lower():
                return {"found": True, "via": "uia"}
        except Exception:
            pass
        # Last resort: select-all → copy (mutates selection/clipboard briefly).
        try:
            prev_ok, prev = get_clipboard()
            prev_text = prev if prev_ok else None
            self.smart_hotkey(["ctrl", "a"])
            time.sleep(0.05)
            self.smart_hotkey(["ctrl", "c"])
            time.sleep(0.08)
            ok, clip = get_clipboard()
            found = bool(ok and sample_l in (clip or "").lower())
            try:
                self.smart_hotkey(["right"])
            except Exception:
                pass
            if prev_text is not None:
                try:
                    set_clipboard(str(prev_text))
                except Exception:
                    pass
            if found:
                return {"found": True, "via": "clipboard"}
        except Exception:
            pass
        return {"found": False, "via": ""}

    def _text_visible_in_focus(self, text: str) -> bool:
        return bool(self._text_in_focus_meta(text).get("found"))

    def smart_type(self, text: str, query: Optional[str] = None, clear: bool = False,
                   confirm: bool = False) -> ActionOutcome:
        t0 = time.time()
        if not getattr(self, "_safety_prechecked", False):
            ok_s, why = self.safety.check("action", text=str(text or ""), confirm=bool(confirm))
            if not ok_s:
                return ActionOutcome(False, False, why, elapsed=0.0, backend=self.backend_name)
        self._metrics["types"] += 1
        focus_target = None
        if query:
            click_out = self.smart_click(query=query, require_change=False)
            if not click_out.success:
                return ActionOutcome(False, False, f"Focus failed for '{query}': {click_out.message}",
                                     elapsed=time.time()-t0, backend=self.backend_name)
            focus_target = click_out.target
            time.sleep(0.1)
        delivery = self._deliver_type(text, clear=clear, target=focus_target)
        # Invalidate a11y so Value/Text patterns re-read document content.
        try:
            self._uia().invalidate(self._focus_pid, self._focus_window_id)
        except Exception:
            pass
        time.sleep(0.12)
        content_ok = False
        via = ""
        backend_used = delivery.backend
        if delivery.ok:
            meta = self._text_in_focus_meta(text)
            content_ok = bool(meta.get("found"))
            via = str(meta.get("via") or "")
            if self.verify and not content_ok:
                deadline = time.time() + 1.2
                while time.time() < deadline and not content_ok:
                    time.sleep(0.12)
                    try:
                        self._uia().invalidate(self._focus_pid, self._focus_window_id)
                    except Exception:
                        pass
                    meta = self._text_in_focus_meta(text)
                    content_ok = bool(meta.get("found"))
                    via = str(meta.get("via") or "")
            # Paste fallback for IME / apps that drop synthetic unicode.
            if self.verify and not content_ok:
                try:
                    prev_ok, prev = get_clipboard()
                    prev_text = prev if prev_ok else None
                    set_clipboard(str(text))
                    if clear:
                        self.smart_hotkey(["ctrl", "a"])
                        time.sleep(0.04)
                    self.smart_hotkey(["ctrl", "v"])
                    time.sleep(0.12)
                    try:
                        self._uia().invalidate(self._focus_pid, self._focus_window_id)
                    except Exception:
                        pass
                    meta = self._text_in_focus_meta(text)
                    content_ok = bool(meta.get("found"))
                    if content_ok:
                        via = str(meta.get("via") or "paste")
                        backend_used = f"{delivery.backend}+paste"
                    if prev_text is not None:
                        try:
                            set_clipboard(str(prev_text))
                        except Exception:
                            pass
                except Exception:
                    pass
        # Honesty: never mark verified from pixel-diff alone (title bar * lied).
        verified = bool(content_ok) if self.verify else bool(delivery.ok)
        msg = f"Typed {len(text)} chars ({backend_used})"
        if delivery.ok and self.verify and not content_ok:
            msg += " — delivery ok but text not visible in a11y (unverified)"
        elif delivery.ok and content_ok:
            msg += f" — verified via {via or 'a11y'}"
        return ActionOutcome(delivery.ok, verified, msg,
                             attempts=1, target=focus_target,
                             elapsed=time.time()-t0, backend=backend_used)

    def _aim_for_wheel(self, query: Optional[str] = None, bbox: Optional[list] = None) -> tuple:
        """Screen point over the document (not the title bar / address bar)."""
        from .pointer import aim_point

        if bbox and len(bbox) >= 4:
            return (int(bbox[0]) + int(bbox[2])) // 2, (int(bbox[1]) + int(bbox[3])) // 2
        if query:
            hits = self.find_targets(query)
            if hits and hits[0].center:
                return int(hits[0].center[0]), int(hits[0].center[1])
        st = self.window_state(self._focus_window_id)
        rect = st.get("rect") if isinstance(st, dict) else None
        if rect and len(rect) == 4:
            title = ""
            try:
                title = str(self._uia().get_tree(self._focus_pid, self._focus_window_id).title or "")
            except Exception:
                title = ""
            chrome = 90 if any(k in title.lower() for k in ("chrome", "edge", "helium", "firefox", "brave")) else 48
            return aim_point(rect, chrome_top=chrome)
        return None, None

    def _wheel_at(self, x: int, y: int, notches: int, h_notches: int = 0) -> bool:
        try:
            from .synthetic.inject_win import wheel_abs
            if wheel_abs(int(x), int(y), int(notches), int(h_notches)):
                return True
        except Exception:
            pass
        try:
            # Fallback: pynput notches (positive = up). Invert our page-down sign.
            if self.local_fallback and getattr(self.local_fallback, "engine", None):
                self.local_fallback.engine.scroll(dx=-int(h_notches), dy=-int(notches), x=x, y=y)
                return True
        except Exception:
            pass
        return False

    def smart_scroll(
        self,
        dy: int = 0,
        dx: int = 0,
        query: Optional[str] = None,
        notches: Optional[int] = None,
        direction: Optional[str] = None,
        amount: Any = None,
        bbox: Optional[list] = None,
    ) -> ActionOutcome:
        from .pointer import parse_scroll

        t0 = time.time()
        req = parse_scroll({
            "dy": dy if dy else None,
            "dx": dx if dx else None,
            "notches": notches,
            "direction": direction,
            "amount": amount,
        })
        nv, nh = req["notches"], req["h_notches"]
        if nv == 0 and nh == 0:
            nv = 3
        x, y = self._aim_for_wheel(query=query, bbox=bbox)
        if x is None or y is None:
            return ActionOutcome(False, False, "no aim point for wheel (focus a window first)",
                                 elapsed=time.time() - t0, backend="synthetic")
        pre = self.observe(modes=["diff"], include_image=False, use_cache=False)
        ok = self._wheel_at(x, y, nv, nh)
        fallback = None
        if not ok:
            # Last resort: PageDown/PageUp. Never Home/End (those jump the caret).
            key = "pagedown" if nv > 0 else "pageup" if nv < 0 else None
            if key:
                try:
                    self.smart_hotkey([key])
                    ok = True
                    fallback = key
                except Exception:
                    pass
        time.sleep(0.12)
        try:
            self._uia().invalidate(self._focus_pid, self._focus_window_id)
        except Exception:
            pass
        post = self.observe(modes=["diff"], include_image=False, use_cache=False)
        changed = self._verify_change(pre, post)
        extra = f" fallback={fallback}" if fallback else ""
        return ActionOutcome(
            ok, changed,
            f"wheel notches={nv} h={nh} at=({x},{y}){extra}",
            elapsed=time.time() - t0,
            backend="synthetic",
        )

    def scroll_into_view(
        self,
        query: Optional[str] = None,
        bbox: Optional[list] = None,
        max_steps: int = 12,
    ) -> Dict[str, Any]:
        """Wheel until query/bbox is inside the focused window document."""
        from .pointer import bbox_visible, notches_toward, viewport_from_rect, NOTCHES_PAGE

        st = self.window_state(self._focus_window_id)
        rect = st.get("rect") if isinstance(st, dict) else None
        if not rect:
            return {"ok": False, "error": "no focused window rect"}
        title = ""
        try:
            title = str(self._uia().get_tree(self._focus_pid, self._focus_window_id).title or "")
        except Exception:
            pass
        chrome = 90 if any(k in title.lower() for k in ("chrome", "edge", "helium", "firefox", "brave")) else 48
        viewport = viewport_from_rect(rect, chrome_top=chrome)
        steps_done = 0
        last_box = list(bbox) if bbox and len(bbox) >= 4 else None
        for i in range(max(1, int(max_steps))):
            if query and not last_box:
                hits = self.find_targets(query)
                if hits and hits[0].bbox:
                    last_box = list(hits[0].bbox)
            if last_box and bbox_visible(last_box, viewport):
                return {
                    "ok": True,
                    "visible": True,
                    "bbox": last_box,
                    "steps": steps_done,
                    "viewport": list(viewport),
                }
            if last_box:
                n = notches_toward(last_box, viewport, step=NOTCHES_PAGE)
            else:
                n = NOTCHES_PAGE
            if n == 0:
                n = NOTCHES_PAGE
            x, y = self._aim_for_wheel(bbox=last_box)
            if x is None:
                return {"ok": False, "error": "no aim point", "steps": steps_done}
            self._wheel_at(x, y, n, 0)
            steps_done += 1
            time.sleep(0.12)
            try:
                self._uia().invalidate(self._focus_pid, self._focus_window_id)
            except Exception:
                pass
            last_box = None
        hits = self.find_targets(query) if query else []
        box = list(hits[0].bbox) if hits and hits[0].bbox else last_box
        vis = bool(box and bbox_visible(box, viewport))
        return {
            "ok": vis,
            "visible": vis,
            "bbox": box,
            "steps": steps_done,
            "viewport": list(viewport),
            "error": None if vis else "target not on screen after wheel",
        }

    def hover(self, query: Optional[str] = None, x: Optional[int] = None, y: Optional[int] = None) -> ActionOutcome:
        t0 = time.time()
        if x is None or y is None:
            if query:
                hits = self.find_targets(query)
                if hits and hits[0].center:
                    x, y = hits[0].center
        if x is None or y is None:
            return ActionOutcome(False, False, "hover needs query or x,y", elapsed=0.0, backend="synthetic")
        try:
            from .synthetic.inject_win import move_human
            ok = move_human(int(x), int(y))
        except Exception as exc:
            return ActionOutcome(False, False, str(exc), elapsed=time.time() - t0, backend="synthetic")
        time.sleep(0.04)
        return ActionOutcome(ok, False, f"hover ({int(x)},{int(y)})", elapsed=time.time() - t0, backend="synthetic")

    def smart_drag(self, start_query: Optional[str] = None, end_query: Optional[str] = None,
                   start: Optional[List[int]] = None, end: Optional[List[int]] = None,
                   duration: float = 0.35) -> ActionOutcome:
        t0 = time.time()
        sxy = start
        exy = end
        if start_query:
            ts = self.find_targets(start_query)
            if not ts or not ts[0].center:
                return ActionOutcome(False, False, f"No start target for {start_query!r}",
                                     elapsed=time.time()-t0, backend=self.backend_name)
            sxy = list(ts[0].center)
        if end_query:
            te = self.find_targets(end_query)
            if not te or not te[0].center:
                return ActionOutcome(False, False, f"No end target for {end_query!r}",
                                     elapsed=time.time()-t0, backend=self.backend_name)
            exy = list(te[0].center)
        if not sxy or not exy or len(sxy) < 2 or len(exy) < 2:
            return ActionOutcome(False, False, "Need start and end", elapsed=time.time()-t0, backend=self.backend_name)
        pre = self.observe(modes=["diff"], include_image=False, use_cache=False)
        try:
            r = self.local_fallback.engine.drag((int(sxy[0]), int(sxy[1])), (int(exy[0]), int(exy[1])), duration=duration)
            ok = getattr(r, "success", True)
        except Exception as e:
            return ActionOutcome(False, False, str(e), elapsed=time.time()-t0, backend="local")
        time.sleep(0.15)
        post = self.observe(modes=["diff"], include_image=False, use_cache=False)
        changed = self._verify_change(pre, post)
        return ActionOutcome(ok, changed, f"Dragged {sxy} → {exy}", elapsed=time.time()-t0, backend="local")

    # Agents write ENTER/ESC/BACKSPACE; pyautogui wants enter/esc/backspace.
    KEY_ALIASES = {
        "control": "ctrl", "ctl": "ctrl", "cmd": "win", "windows": "win", "super": "win",
        "return": "enter", "escape": "esc", "del": "delete", "ins": "insert",
        "pgup": "pageup", "pgdn": "pagedown", "spacebar": "space",
        "arrowup": "up", "arrowdown": "down", "arrowleft": "left", "arrowright": "right",
        "bksp": "backspace", "back": "backspace",
    }

    def _normalize_keys(self, keys: List[str]) -> List[str]:
        out = []
        for k in keys or []:
            key = str(k).strip().lower()
            out.append(self.KEY_ALIASES.get(key, key))
        return out

    def smart_hotkey(self, keys: List[str], confirm: bool = False) -> ActionOutcome:
        t0 = time.time()
        norm = self._normalize_keys(keys)
        if not norm:
            return ActionOutcome(False, False, "no keys", elapsed=0.0, backend=self.backend_name)
        joined = " ".join(norm)
        if not getattr(self, "_safety_prechecked", False):
            ok_s, why = self.safety.check("action", text=joined, confirm=bool(confirm))
            if not ok_s:
                return ActionOutcome(False, False, why, elapsed=0.0, backend=self.backend_name)
        r = self.backend.hotkey(norm) if hasattr(self.backend, "hotkey") else self.local_fallback.hotkey(norm)
        if not r.ok and self.backend.name != "local":
            r = self.local_fallback.hotkey(norm)
        self._record_stat("smart_hotkey", time.time() - t0, ok=r.ok)
        return ActionOutcome(r.ok, True, r.message or f"hotkey {norm}",
                             elapsed=time.time()-t0, backend=r.backend)

    def batch(self, actions: List[Dict[str, Any]], stop_on_failure: bool = True) -> Dict[str, Any]:
        """
        Execute a list of actions quickly.
        Each action: {"op": "click"|"type"|"scroll"|"hotkey"|"wait", ...params}
        Shares memory and avoids redundant full observes when possible.
        """
        t0 = time.time()
        self._metrics["batches"] += 1
        results = []
        for i, act in enumerate(actions):
            op = (act.get("op") or act.get("action") or "").lower()
            try:
                if op == "click":
                    out = self.smart_click(
                        query=act.get("query"), x=act.get("x"), y=act.get("y"),
                        button=act.get("button", "left"),
                        require_change=act.get("require_change", False),
                    )
                elif op == "type":
                    out = self.smart_type(text=act.get("text", ""), query=act.get("query"), clear=act.get("clear", False))
                elif op == "scroll":
                    out = self.smart_scroll(
                        dy=act.get("dy") or 0,
                        dx=act.get("dx") or 0,
                        query=act.get("query"),
                        notches=act.get("notches"),
                        direction=act.get("direction") or act.get("dir"),
                        amount=act.get("amount"),
                    )
                elif op in {"scroll_into_view", "into_view"}:
                    out = self.scroll_into_view(query=act.get("query"), bbox=act.get("bbox"))
                elif op == "hover":
                    out = self.hover(query=act.get("query"), x=act.get("x"), y=act.get("y"))
                elif op == "hotkey":
                    out = self.smart_hotkey(act.get("keys") or [])
                elif op == "drag":
                    out = self.smart_drag(
                        start_query=act.get("start_query"), end_query=act.get("end_query"),
                        start=act.get("start"), end=act.get("end"),
                        duration=act.get("duration", 0.35),
                    )
                elif op == "wait":
                    time.sleep(float(act.get("seconds", 0.5)))
                    out = ActionOutcome(True, True, f"waited {act.get('seconds', 0.5)}s", backend=self.backend_name)
                elif op == "observe":
                    obs = self.observe(include_image=act.get("include_image", False))
                    results.append({"index": i, "op": op, "success": True, "obs_id": obs.get("obs_id")})
                    continue
                else:
                    out = ActionOutcome(False, False, f"unknown op {op}", backend=self.backend_name)
                entry = {
                    "index": i, "op": op, "success": out.success, "verified": out.verified,
                    "message": out.message, "backend": out.backend, "elapsed": round(out.elapsed, 3),
                }
                results.append(entry)
                if stop_on_failure and not out.success:
                    break
            except Exception as e:
                results.append({"index": i, "op": op, "success": False, "message": str(e)})
                if stop_on_failure:
                    break
        ok = all(r.get("success") for r in results) if results else False
        return {"ok": ok, "count": len(results), "elapsed": round(time.time() - t0, 3), "results": results}

    def do(self, goal: str, max_steps: int = 8) -> Dict[str, Any]:
        history = []
        for step in range(max_steps):
            out = self.smart_click(query=goal, require_change=False)
            history.append({"step": step, "success": out.success, "message": out.message, "backend": out.backend})
            if out.success:
                return {"ok": True, "steps": history, "final": out.message}
            if "No targets" in out.message:
                break
        return {"ok": False, "steps": history, "final": "exhausted"}


    def _target_alive(self, pid: Optional[int] = None, hwnd: Optional[int] = None) -> Dict[str, Any]:
        """Fast check: focused process/HWND still exist. Never blocks on UIA."""
        import sys
        pid = pid if pid is not None else self._focus_pid
        hwnd = hwnd if hwnd is not None else self._focus_window_id
        if sys.platform != "win32":
            return {"alive": True, "pid": pid, "hwnd": hwnd}
        try:
            import ctypes
            from ctypes import wintypes
            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32
            if hwnd is not None:
                try:
                    if not user32.IsWindow(int(hwnd)):
                        return {"alive": False, "reason": "hwnd_dead", "pid": pid, "hwnd": hwnd}
                except Exception:
                    return {"alive": False, "reason": "hwnd_check_failed", "pid": pid, "hwnd": hwnd}
            if pid is not None:
                PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
                handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
                if not handle:
                    return {"alive": False, "reason": "pid_dead", "pid": pid, "hwnd": hwnd}
                try:
                    code = wintypes.DWORD()
                    if kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                        # STILL_ACTIVE = 259
                        if int(code.value) != 259:
                            return {"alive": False, "reason": "pid_exited", "pid": pid, "hwnd": hwnd,
                                    "exit_code": int(code.value)}
                finally:
                    kernel32.CloseHandle(handle)
            return {"alive": True, "pid": pid, "hwnd": hwnd}
        except Exception as exc:
            return {"alive": False, "reason": f"check_error:{type(exc).__name__}", "pid": pid, "hwnd": hwnd}

    def _uia_call(self, fn, timeout_s: float = 2.5, default=None):
        """Run a UIA-touching callable with a hard timeout (dead targets hang COM)."""
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            fut = pool.submit(fn)
            try:
                return fut.result(timeout=max(0.2, float(timeout_s)))
            except concurrent.futures.TimeoutError:
                return default
            except Exception:
                return default

    def wait_until(
        self,
        query: Optional[str] = None,
        text_contains: Optional[str] = None,
        timeout: float = 15.0,
        poll: float = 0.45,
    ) -> ActionOutcome:
        """Wait until a target appears. Polls the a11y tree, not screenshots."""
        t0 = time.time()
        self._metrics["waits"] += 1
        needle = (text_contains or query or "").strip()
        if not needle:
            return ActionOutcome(False, False, "need query or text_contains", elapsed=0, backend=self.backend_name)
        needle_l = needle.lower()
        timeout = min(float(timeout), 15.0)
        while time.time() - t0 < timeout:
            alive = self._target_alive()
            if not alive.get("alive"):
                return ActionOutcome(
                    False, False,
                    f"target window dead ({alive.get('reason')})",
                    elapsed=time.time() - t0, backend=self.backend_name,
                )
            hit = self._find_visible_label(needle_l)
            if hit is not None:
                return ActionOutcome(
                    True, True,
                    f"Found '{hit.label}' [{(hit.meta or {}).get('role') or '?'}] at ({hit.x},{hit.y})",
                    target=hit, elapsed=time.time() - t0, backend=self.backend_name,
                )
            # OCR only once a11y has had a fair chance — it costs ~1s a pass.
            if time.time() - t0 > timeout / 2:
                obs = self._uia_call(
                    lambda: self.observe(modes=["ocr", "vision"], include_image=False, use_cache=False),
                    timeout_s=2.5, default=None,
                )
                if isinstance(obs, dict):
                    ocr_text = " ".join(
                        (i.get("text") or "") for i in obs.get("vision", {}).get("ocr", [])
                    ).lower()
                    if needle_l in ocr_text:
                        return ActionOutcome(True, True, f"Text visible via OCR: {needle}",
                                             elapsed=time.time() - t0, backend=self.backend_name)
            time.sleep(poll)
        self._record_stat("wait_until", time.time() - t0, ok=False)
        return ActionOutcome(False, False, f"Timeout waiting for '{needle}'", elapsed=time.time() - t0, backend=self.backend_name)

    def _find_visible_label(self, needle_l: str) -> Optional[Target]:
        """First a11y element whose name or value contains needle (document text counts)."""
        if self._focus_pid is None:
            return None
        try:
            tree = self._uia_call(
                lambda: self._uia().get_tree(self._focus_pid, self._focus_window_id, force=True),
                timeout_s=2.5, default=None,
            )
            if tree is None:
                return None
        except Exception:
            return None
        for el in tree.elements:
            name = el.name or ""
            value = getattr(el, "value", "") or ""
            hit_field = None
            via = "name"
            if name and needle_l in name.lower():
                hit_field = name
            elif value and needle_l in value.lower():
                hit_field = value if len(value) <= 80 else value[:77] + "..."
                via = "value"
            if not hit_field:
                continue
            # Document/value hits may have odd offscreen bounds; still accept.
            if not el.on_screen and via == "name":
                continue
            t = Target(
                kind="a11y", label=hit_field, bbox=el.bbox, confidence=0.95,
                source="uia-cache", pid=self._focus_pid, window_id=self._focus_window_id,
                element_index=el.index, meta={"role": el.role, "cached": el, "via": via},
            )
            if t.bbox and t.center:
                t.x, t.y = t.center
            return t
        return None

    def verify_ui(self, expect: Optional[List[str]] = None,
                  expect_gone: Optional[List[str]] = None,
                  timeout: float = 6.0, poll: float = 0.25) -> Dict[str, Any]:
        """Assert on-screen state and return the evidence, not just a verdict.

        Fail-closed: if expected text/controls are absent when timeout elapses,
        returns ok=False (never a vacuous pass for a non-empty expect list).
        """
        t0 = time.time()
        if isinstance(expect, str):
            expect = [expect]
        if isinstance(expect_gone, str):
            expect_gone = [expect_gone]
        expect = [e for e in (expect or []) if str(e).strip()]
        expect_gone = [e for e in (expect_gone or []) if str(e).strip()]
        if not expect and not expect_gone:
            return {
                "ok": False,
                "found": {},
                "missing": [],
                "still_present": [],
                "error": "verify requires expect or expect_gone",
                "elapsed": 0.0,
            }
        found: Dict[str, Any] = {}
        missing: List[str] = []
        still_present: List[str] = []
        deadline = time.time() + timeout
        while True:
            found = {}
            missing = []
            still_present = []
            for needle in expect:
                hit = self._find_visible_label(str(needle).lower())
                if hit is not None:
                    found[needle] = {"label": hit.label,
                                     "role": (hit.meta or {}).get("role"),
                                     "at": [hit.x, hit.y],
                                     "via": (hit.meta or {}).get("via") or "name"}
                    continue
                # Document body: Value/Text/Win32 first; clipboard last.
                meta = self._text_in_focus_meta(str(needle))
                if meta.get("found"):
                    found[needle] = {
                        "label": str(needle),
                        "role": "document",
                        "at": [None, None],
                        "via": meta.get("via") or "content",
                    }
                else:
                    missing.append(needle)
            for needle in expect_gone:
                if self._find_visible_label(str(needle).lower()) is not None:
                    still_present.append(needle)
                elif self._text_in_focus_meta(str(needle)).get("found"):
                    still_present.append(needle)
            if not missing and not still_present:
                break
            if time.time() >= deadline:
                break
            time.sleep(poll)
        ok = not missing and not still_present
        self._record_stat("verify_ui", time.time() - t0, ok=ok)
        return {
            "ok": ok,
            "found": found,
            "missing": missing,
            "still_present": still_present,
            "title": self._uia().get_tree(self._focus_pid, self._focus_window_id).title
            if self._focus_pid else "",
            "window": self.window_state(self._focus_window_id),
            "elapsed": round(time.time() - t0, 3),
        }

    def smart_fill(self, fields: Dict[str, str], submit: Optional[str] = None, clear: bool = True) -> Dict[str, Any]:
        """
        Fill a form: fields = {"Email": "a@b.com", "Password": "x"}.
        Optionally click submit query after.
        """
        t0 = time.time()
        self._metrics["fills"] += 1
        results = []
        for label, value in fields.items():
            out = self.smart_type(text=str(value), query=str(label), clear=clear)
            results.append({"field": label, "success": out.success, "message": out.message, "elapsed": round(out.elapsed, 3)})
            if not out.success:
                return {"ok": False, "results": results, "elapsed": round(time.time() - t0, 3)}
            time.sleep(0.08)
        if submit:
            out = self.smart_click(query=submit)
            results.append({"field": f"submit:{submit}", "success": out.success, "message": out.message})
            return {"ok": out.success, "results": results, "elapsed": round(time.time() - t0, 3)}
        return {"ok": True, "results": results, "elapsed": round(time.time() - t0, 3)}

    def clipboard_get(self) -> Dict[str, Any]:
        ok, val = get_clipboard()
        return {"ok": ok, "text": val if ok else "", "error": None if ok else val}

    def clipboard_set(self, text: str) -> Dict[str, Any]:
        ok, msg = set_clipboard(text)
        return {"ok": ok, "message": msg}

    def kill_switch(self, armed: bool = True) -> Dict[str, Any]:
        if armed:
            self.safety.arm_kill_switch()
        else:
            self.safety.disarm_kill_switch()
        return {"kill_switch": self.safety.config.kill_switch}


    def observe_annotated(self, max_labels: int = 30, max_image_side: int = 1280) -> Dict[str, Any]:
        """Observe and return screenshot with grounded boxes drawn (debug eyes)."""
        obs = self.observe(modes=["vision", "ocr"], include_image=True, max_image_side=max_image_side, use_cache=False)
        elements = obs.get("vision", {}).get("elements", []) or []
        # Try to annotate from raw if available; else return elements only
        annotated = None
        try:
            # re-capture for pixels
            img = self.perception.capture(monitor=self._focus_monitor or 1)
            if img is not None:
                annotated = annotate_to_base64(img, elements, quality=65)
        except Exception:
            annotated = None
        return {
            "obs_id": obs.get("obs_id"),
            "elements": elements[:max_labels],
            "annotated_screenshot_base64": annotated,
            "element_count": len(elements),
        }

    def recent_actions(self, n: int = 20) -> List[Dict[str, Any]]:
        return self.log.tail(n)


    def smart_focus(
        self,
        title: Optional[str] = None,
        pid: Optional[int] = None,
        monitor: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Focus a window by title substring or pid; sets a11y context for subsequent clicks.

        When ``monitor`` is set, only windows whose center/overlap lives on that
        display are candidates; miss = fail closed with monitor inventory.
        """
        from .monitors import filter_windows_for_monitor, monitor_bind_error, window_on_monitor, get_monitor

        windows = self.list_windows()
        mon_info = None
        mon_id = int(monitor) if monitor is not None else None
        if mon_id is not None:
            filtered, mon_info = filter_windows_for_monitor(windows, mon_id)
            if mon_info is None:
                return monitor_bind_error(mon_id, "unknown monitor id")
            windows = filtered
        match = None
        if pid is not None:
            for w in windows:
                if int(w.get("pid") or w.get("handle") or -1) == int(pid) or int(w.get("pid") or -1) == int(pid):
                    match = w
                    break
        if match is None and title:
            t = title.lower()
            candidates = []
            for w in windows:
                wt = str(w.get("title") or w.get("name") or "").lower()
                if t not in wt:
                    continue
                cls = str(w.get("class_name") or "").lower()
                # Prefer real app hosts over embedded WebView2/Chrome child windows.
                rank = 0
                if "winui" in cls or "hwndwrapper" in cls or cls.endswith("window"):
                    rank += 2
                if "chrome_widgetwin" in cls or "webview" in cls:
                    rank -= 2
                if w.get("visible") and not w.get("minimized"):
                    rank += 1
                candidates.append((rank, w))
            if candidates:
                candidates.sort(key=lambda item: item[0], reverse=True)
                match = candidates[0][1]
        if match is None:
            if mon_id is not None:
                return monitor_bind_error(
                    mon_id,
                    "no window on monitor" + (f" matching {title!r}" if title else ""),
                )
            return {"ok": False, "error": "window not found", "windows": windows[:12]}
        if mon_info is not None and not window_on_monitor(match, mon_info):
            return monitor_bind_error(mon_id or 0, "matched window not on requested monitor")
        wpid = match.get("pid") or match.get("process_id")
        wid = match.get("window_id") or match.get("handle")
        try:
            wpid = int(wpid) if wpid is not None else None
        except Exception:
            wpid = None
        try:
            wid = int(wid) if wid is not None else None
        except Exception:
            wid = None
        raised = False
        if wpid is not None:
            fr = self.focus_window(wpid, wid)
            raised = bool(fr.get("raised"))
        self._focus_monitor = mon_id
        if self.macros.is_recording():
            self.macros.add("focus", title=title, pid=wpid, window_id=wid, monitor=mon_id)
        out = {
            "ok": True, "pid": wpid, "window_id": wid,
            "title": match.get("title") or match.get("name"),
            "raised": raised,
            "rect": match.get("rect"),
        }
        if mon_id is not None:
            out["monitor"] = mon_id
            out["monitor_info"] = mon_info or get_monitor(mon_id)
        return out

    def wait_gone(self, query: str, timeout: float = 15.0, poll: float = 0.45) -> ActionOutcome:
        """Wait until a target is not visible (a11y/OCR). Dead target window counts as gone."""
        t0 = time.time()
        timeout = min(float(timeout), 15.0)
        self._metrics["waits"] = self._metrics.get("waits", 0) + 1
        needle_l = (query or "").strip().lower()
        while time.time() - t0 < timeout:
            alive = self._target_alive()
            if not alive.get("alive"):
                # Visibility: no window => control is not visible.
                return ActionOutcome(
                    True, True,
                    f"Gone (target window dead): {query}",
                    elapsed=time.time() - t0, backend=self.backend_name,
                )
            hit = self._find_visible_label(needle_l) if needle_l else None
            if hit is None:
                # Confirm with a bounded OCR pass only if a11y miss
                obs = self._uia_call(
                    lambda: self.observe(modes=["ocr"], include_image=False, use_cache=False),
                    timeout_s=2.0, default={},
                ) or {}
                ocr_text = " ".join(
                    (i.get("text") or "") for i in (obs.get("vision") or {}).get("ocr", [])
                ).lower()
                if needle_l and needle_l in ocr_text:
                    time.sleep(poll)
                    continue
                return ActionOutcome(True, True, f"Gone: {query}", elapsed=time.time() - t0, backend=self.backend_name)
            time.sleep(poll)
        return ActionOutcome(False, False, f"Still present: {query}", elapsed=time.time() - t0, backend=self.backend_name)

    def wait_change(self, timeout: float = 10.0, poll: float = 0.35, threshold: Optional[float] = None,
                    expect: Optional[Any] = None) -> ActionOutcome:
        """Wait until the screen changes, or until expected text appears.

        Fail-closed: when expect/text is provided and never appears, returns success=False.
        If the focused HWND/process dies, fails fast (no UIA hang).
        """
        t0 = time.time()
        timeout = min(float(timeout), 15.0)
        needle = None
        if isinstance(expect, (list, tuple)):
            parts = [str(x).strip() for x in expect if str(x).strip()]
            needle = parts[0] if parts else None
        elif expect is not None:
            needle = str(expect).strip() or None
        if needle:
            out = self.wait_until(text_contains=needle, timeout=timeout, poll=poll)
            if not out.success:
                msg = out.message or ""
                if "target window dead" in msg:
                    return ActionOutcome(False, False, msg, elapsed=out.elapsed, backend=self.backend_name)
                return ActionOutcome(False, False, f"wait_change expected text absent: {needle}",
                                     elapsed=out.elapsed, backend=self.backend_name)
            return out
        thr = threshold if threshold is not None else self.similarity_threshold
        pre = self._uia_call(
            lambda: self.observe(modes=["diff"], include_image=False, use_cache=False),
            timeout_s=2.5, default=None,
        )
        if pre is None:
            alive = self._target_alive()
            if not alive.get("alive"):
                return ActionOutcome(False, False, f"target window dead ({alive.get('reason')})",
                                     elapsed=time.time() - t0, backend=self.backend_name)
        while time.time() - t0 < timeout:
            alive = self._target_alive()
            if not alive.get("alive"):
                return ActionOutcome(
                    False, False,
                    f"target window dead ({alive.get('reason')})",
                    elapsed=time.time() - t0, backend=self.backend_name,
                )
            time.sleep(poll)
            post = self._uia_call(
                lambda: self.observe(modes=["diff"], include_image=False, use_cache=False),
                timeout_s=2.5, default=None,
            )
            if post is None:
                continue
            if pre is not None and self._verify_change(pre, post):
                return ActionOutcome(True, True, "Screen changed", elapsed=time.time() - t0, backend=self.backend_name)
        return ActionOutcome(False, False, "No change detected", elapsed=time.time() - t0, backend=self.backend_name)

    def compact_observe(
        self,
        include_ocr: bool = False,
        max_ocr: int = 40,
        max_elements: int = 30,
        monitor: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Token-efficient observation for LLM agents (a11y-first, optional OCR).

        When ``monitor`` is set, OCR/vision bind to that display. If a window is
        focused and does not live on that monitor, fail closed.
        """
        from .monitors import get_monitor, monitor_bind_error, rect_on_monitor

        t0 = time.time()
        mon_id = int(monitor) if monitor is not None else self._focus_monitor
        mon_info = get_monitor(mon_id) if mon_id is not None else None
        if mon_id is not None and mon_info is None:
            return monitor_bind_error(mon_id, "unknown monitor id")

        # Only fail-closed on explicit agent focus — read_ui may adopt the
        # foreground HWND and must not poison monitor-bound OCR.
        explicit_focus = self._focus_pid is not None or self._focus_window_id is not None
        if mon_info is not None and explicit_focus:
            rect = self._focus_rect
            try:
                st = self.window_state(self._focus_window_id)
                if isinstance(st, dict) and st.get("rect"):
                    rect = st.get("rect")
            except Exception:
                pass
            if rect and not rect_on_monitor(rect, mon_info):
                return monitor_bind_error(
                    int(mon_id),
                    "focused window not on requested monitor",
                )

        ui = self.read_ui()

        ocr: List[Dict[str, Any]] = []
        els: List[Dict[str, Any]] = []
        if include_ocr:
            # Prefer realtime buffer if running; else one cheap OCR pass
            eyes = self._get_eyes()
            if eyes._running and mon_id is None:
                frame = eyes.read_now(force_ocr=False)
                ocr = frame.get("labels") or []
            else:
                obs_kw: Dict[str, Any] = {"modes": ["ocr"], "include_image": False, "use_cache": True}
                if mon_id is not None:
                    obs_kw["monitor"] = int(mon_id)
                    obs_kw["use_cache"] = False
                obs = self.observe(**obs_kw)
                ocr = (obs.get("vision") or {}).get("ocr") or []
                els = (obs.get("vision") or {}).get("elements") or []
        a11y_els = ui.get("elements") or []
        a11y_compact = []
        for e in a11y_els[:max_elements]:
            item = {
                "label": e.get("name"),
                "role": e.get("role"),
                "bbox": e.get("bbox"),
                "element_index": e.get("element_index"),
            }
            if e.get("value"):
                item["value"] = e.get("value")
            a11y_compact.append(item)
        out: Dict[str, Any] = {
            "ok": True,
            "backend": self.backend_name,
            "focus_pid": self._focus_pid or ui.get("pid"),
            "title": ui.get("title"),
            "a11y_labels": (ui.get("labels") or [])[:max_elements],
            "a11y_values": (ui.get("values") or [])[:max_elements],
            "a11y_value_entries": (ui.get("value_entries") or [])[:max_elements],
            "a11y": a11y_compact,
            "ocr": [
                {"text": i.get("text"), "conf": i.get("confidence") or i.get("conf"), "bbox": i.get("bbox")}
                for i in ocr[:max_ocr]
            ],
            "elements": [
                {"label": e.get("label"), "kind": e.get("kind"), "conf": e.get("confidence"),
                 "bbox": e.get("bbox"), "source": e.get("source")}
                for e in els[:max_elements]
            ],
            "ocr_count": len(ocr),
            "element_count": len(els),
            "a11y_count": len(a11y_els),
            "elapsed": round(time.time() - t0, 3),
            "cached_tree": True,
        }
        if mon_id is not None:
            out["monitor"] = int(mon_id)
            out["monitor_info"] = mon_info
        return out

    def stats(self, reset: bool = False) -> Dict[str, Any]:
        """Live latency and reliability counters for the current session."""
        def pct(samples: List[float], q: float) -> float:
            if not samples:
                return 0.0
            ordered = sorted(samples)
            idx = min(len(ordered) - 1, int(round(q * (len(ordered) - 1))))
            return ordered[idx]

        ops = {}
        for op, bucket in self._timings.items():
            samples = bucket["ms"]
            ops[op] = {
                "calls": bucket["n"],
                "failures": bucket["fail"],
                "p50_ms": round(pct(samples, 0.5), 1),
                "p95_ms": round(pct(samples, 0.95), 1),
                "max_ms": round(max(samples), 1) if samples else 0.0,
            }
        cache = self._uia().stats
        total_lookups = cache["hits"] + cache["misses"]
        out = {
            "uptime_s": round(time.time() - self._started_at, 1),
            "backend": self.backend_name,
            "focus_pid": self._focus_pid,
            "focus_window": self.window_state(self._focus_window_id),
            "ops": ops,
            "counters": dict(self._metrics),
            "uia_cache": {
                **cache,
                "hit_rate": round(cache["hits"] / total_lookups, 3) if total_lookups else 0.0,
            },
            "eyes_running": bool(self._eyes and getattr(self._eyes, "_running", False)),
        }
        if reset:
            self._timings.clear()
            for k in self._metrics:
                self._metrics[k] = 0
        return out

    def macro_start(self) -> Dict[str, Any]:
        self.macros.start()
        return {"ok": True, "recording": True}

    def macro_stop(self, save_as: Optional[str] = None) -> Dict[str, Any]:
        actions = self.macros.stop()
        path = None
        if save_as:
            path = str(self.macros.save(save_as, actions))
        return {"ok": True, "count": len(actions), "actions": actions, "saved": path}

    def macro_play(self, name: str, stop_on_failure: bool = True) -> Dict[str, Any]:
        actions = self.macros.load(name)
        # Map focus ops
        mapped = []
        for a in actions:
            op = a.get("op")
            if op == "focus":
                self.smart_focus(title=a.get("title"), pid=a.get("pid"))
                mapped.append({"op": "wait", "seconds": 0.2})
            else:
                mapped.append(a)
        return self.batch(mapped, stop_on_failure=stop_on_failure)

    def macro_list(self) -> List[str]:
        return self.macros.list()



    def cursor(self, cursor_id: str = "main") -> "CursorHandle":
        """Return a handle that enqueues actions on a named cursor queue."""
        created = self.create_cursor(cursor_id)
        if isinstance(created, dict) and created.get("ok") is False:
            raise RuntimeError(created.get("error") or "create_cursor failed")
        return CursorHandle(self, cursor_id)

    def cursor_exec(self, cursor_id: str, steps: Any, stop_on_failure: bool = True) -> Dict[str, Any]:
        """Run declarative steps on a named cursor queue (serial mid-action across cursors)."""
        from exo_control.exec_engine import AetherExecEngine
        self.create_cursor(cursor_id)
        eng = AetherExecEngine(controller=self)
        # Tag steps so injects can route via backend cursor_id when present.
        parsed = AetherExecEngine.parse(steps)
        for step in parsed:
            step.setdefault("cursor_id", cursor_id)
        # Submit whole script as one mid-action-safe job on that cursor queue.
        backend = self.backend
        if hasattr(backend, "queues"):
            def _job():
                return eng.execute(parsed, stop_on_failure=stop_on_failure)
            result = backend.queues.get(cursor_id).submit(_job, timeout=120.0)
            if isinstance(result, dict):
                result.setdefault("cursor_id", cursor_id)
                return result
            return {"ok": False, "error": str(result), "cursor_id": cursor_id}
        return eng.execute(parsed, stop_on_failure=stop_on_failure)


    def list_cursors(self) -> List[Dict[str, Any]]:
        if hasattr(self.backend, "list_cursors"):
            return self.backend.list_cursors()
        return []

    def create_cursor(self, cursor_id: str) -> Dict[str, Any]:
        if hasattr(self.backend, "create_cursor"):
            out = self.backend.create_cursor(cursor_id)
            if isinstance(out, dict):
                out.setdefault("ok", True)
                out.setdefault("id", cursor_id)
                out["cursor_id"] = cursor_id
                out["queue"] = True
            return out
        # Soft fallback: still allow cursor_exec against QueueHub if backend exposes queues
        if hasattr(self.backend, "queues"):
            self.backend.queues.get(cursor_id)
            return {"ok": True, "id": cursor_id, "cursor_id": cursor_id, "queue": True}
        return {"ok": False, "error": "backend does not support multi-cursor"}

    def queue_stats(self) -> Dict[str, Any]:
        if hasattr(self.backend, "queue_stats"):
            return self.backend.queue_stats()
        return {}


    def status(self) -> Dict[str, Any]:
        import sys
        cua_ok = isinstance(self.backend, CuaBackend)
        eyes_running = bool(self._eyes and getattr(self._eyes, "_running", False))
        ocr_ready = False
        try:
            ocr_ready = bool(getattr(self.perception, "ocr_available", lambda: False)())
        except Exception:
            ocr_ready = False
        return {
            "ok": True,
            "version": __import__("aether").__version__,
            "engine": "ExoExecEngine",
            "backend": self.backend_name,
            "backend_class": type(self.backend).__name__,
            "cua_active": cua_ok,
            "verify": self.verify,
            "max_retries": self.max_retries,
            "focus_pid": self._focus_pid,
            "focus_window_id": self._focus_window_id,
            "browser": HAS_BROWSER,
            "eyes_running": eyes_running,
            "memory": self.memory.stats(),
            "safety": self.safety.stats(),
            "macro_recording": self.macros.is_recording(),
            "queues": self.queue_stats() if hasattr(self, "queue_stats") else {},
            "macros": self.macros.list(),
            "metrics": dict(self._metrics),
            "cache_ttl": getattr(self.perception, "_obs_cache_ttl", None),
            "capabilities": {
                "a11y_element_clicks": True,
                "uia_tree_cache": True,
                "uia_value_text": True,
                "realtime_eyes": True,
                "read_ui": True,
                "exo_cdp_discover": True,
                "background_hands": True,
                "local_ui_grounding": True,
                "ocr_grounding": ocr_ready,
                "frame_diff_verify": True,
                "auto_retry": True,
                "ui_memory": True,
                "ui_memory_persist": True,
                "multi_monitor": True,
                "observation_cache": True,
                "batch_actions": True,
                "wait_until": True,
                "smart_fill": True,
                "clipboard": True,
                "kill_switch": True,
                "pywinauto_windows": sys.platform == "win32",
                "action_log": True,
                "observe_annotated": True,
                "cdp_attach": True,
                "smart_focus": True,
                "wait_gone": True,
                "wait_change": True,
                "compact_observe": True,
                "macros": True,
                "synthetic_hands": True,
                "virtual_cursors": True,
                "uia_invoke": sys.platform == "win32",
                "ax_mac": sys.platform == "darwin",
                "parallel_cursor_queues": True,
                "start_menu_launch": sys.platform == "win32",
                "smart_scroll_drag": True,
                "sendinput_wheel": True,
                "scroll_into_view": True,
                "hover": True,
                "live_eyes": True,
                "windows_browser_spaces": HAS_BROWSER,
            },
        }


class CursorHandle:
    """Enqueue smart_* actions onto a named cursor without mid-action interleave."""

    def __init__(self, ctrl: "SmartController", cursor_id: str):
        self.ctrl = ctrl
        self.cursor_id = cursor_id

    def smart_click(self, **kwargs):
        return self.ctrl.cursor_exec(self.cursor_id, [{"op": "click", **kwargs}])

    def smart_type(self, text: str = "", **kwargs):
        step = {"op": "type", "text": text, **kwargs}
        return self.ctrl.cursor_exec(self.cursor_id, [step])

    def smart_hotkey(self, keys=None, **kwargs):
        step = {"op": "keys", "keys": keys or [], **kwargs}
        return self.ctrl.cursor_exec(self.cursor_id, [step])

    def exec(self, steps, stop_on_failure: bool = True):
        return self.ctrl.cursor_exec(self.cursor_id, steps, stop_on_failure=stop_on_failure)

