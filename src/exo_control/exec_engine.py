"""Compact, script-first execution surface for Aether.

The full Aether MCP remains useful for interactive discovery.  This module is
the low-token surface: an agent sends one declarative JSON script, Aether keeps
its controller/cache alive, and every step returns compact verification data.
"""
from __future__ import annotations

import base64
from pathlib import Path
import io
import json
import time
from collections.abc import Mapping, Sequence
from typing import Any, Dict, List, Optional

from exo_control.smart import SmartController
from exo_control import desktop_lease
from exo_control.compact import compact_payload, MAX_COMPACT_CHARS
from exo_control import files_ops
from exo_control import registry_ops
from exo_control import infra_ops
from exo_control.ops_catalog import lease_free_ops, lease_required_ops
from exo_control.policy import (
    allow_screenshot_on_fail_default,
    deny_browser_eval,
    identity,
    is_dangerous_launch,
    live_eyes_enabled,
    open_needs_confirm,
    parse_confirm,
    sanitize_cdp_endpoints,
)


MAX_STEPS = 64
MAX_WAIT_SECONDS = 60.0

# Generated from ops_catalog.OPS — do not hand-edit.
LEASE_REQUIRED_OPS = lease_required_ops() | frozenset({
    "window", "window_state", "shot",
})
LEASE_FREE_OPS = lease_free_ops()


def _lease_denied() -> Dict[str, Any]:
    return {"ok": False, "error": "desktop lease required"}


def _action_result(value: Any) -> Dict[str, Any]:
    target = getattr(value, "target", None)
    target_out = None
    if target is not None:
        meta = getattr(target, "meta", None) or {}
        target_out = {
            "label": getattr(target, "label", None),
            "role": meta.get("role"),
            "confidence": round(float(getattr(target, "confidence", 0.0)), 3),
            "at": [getattr(target, "x", None), getattr(target, "y", None)],
        }
    success = bool(getattr(value, "success", False))
    out: Dict[str, Any] = {
        "ok": success,
        "success": success,
        "message": getattr(value, "message", ""),
    }
    for name in ("verified", "backend", "attempts", "from_memory"):
        if hasattr(value, name):
            out[name] = getattr(value, name)
    if target_out is not None:
        out["target"] = target_out
    return out


def _failed(value: Any) -> bool:
    if not isinstance(value, Mapping):
        return False
    return value.get("ok") is False or value.get("success") is False


def _step_ok(value: Any) -> bool:
    """Normalize step success for the step envelope (agents parse step.ok)."""
    if not isinstance(value, Mapping):
        return True
    if value.get("ok") is False or value.get("success") is False:
        return False
    if value.get("ok") is True or value.get("success") is True:
        return True
    if value.get("error") or value.get("blocked"):
        return False
    # status/capabilities-style payloads without explicit ok → success
    return True


def _normalize_result(op: str, value: Any) -> Dict[str, Any]:
    """Every exec step result is a dict with an ``ok`` field."""
    if isinstance(value, list):
        if op in {"windows", "list_windows"}:
            return {"ok": True, "windows": value, "count": len(value)}
        if op == "apps":
            return {"ok": True, "apps": value, "count": len(value)}
        return {"ok": True, "items": value, "count": len(value)}
    if isinstance(value, Mapping):
        out = dict(value)
        if "ok" not in out:
            if out.get("success") is False or out.get("error") or out.get("blocked"):
                out["ok"] = False
            elif out.get("success") is True:
                out["ok"] = True
            else:
                out["ok"] = True
        return out
    if value is None:
        return {"ok": True}
    return {"ok": True, "value": value}


class ExoExecEngine:
    """Persistent desktop/browser controller (MCP / CLI / Python). Preferred name."""

    def __init__(self, controller: Optional[SmartController] = None):
        self.ctrl = controller or SmartController(
            prefer_cua=None, max_retries=3, verify=True, cache_ttl=0.35
        )
        self._browser = None
        self._script_lease_token: Optional[str] = None
        self._action_log: List[Dict[str, Any]] = []
        self._last_browser_refs: List[Any] = []
        self._desktop_refs: Dict[str, Dict[str, Any]] = {}
        self._last_error: Optional[Dict[str, Any]] = None
        self._script_launched_pids: List[int] = []
        self._eyes_started_by_lease = False
        self._browser_use_session: Optional[str] = None

    def _get_browser(self):
        if self._browser is None:
            from exo_control.browser import BrowserEngineSync

            # Do NOT call start() here. start() launches a fresh Chromium profile and
            # breaks later browser_connect (CDP attach). Non-CDP callers still trigger
            # start via ensure_started() on first navigate/snapshot.
            self._browser = BrowserEngineSync(headless=False)
        return self._browser

    @staticmethod
    def parse(script: Any) -> List[Dict[str, Any]]:
        steps, _finally = ExoExecEngine.parse_document(script)
        return steps

    @staticmethod
    def parse_document(script: Any) -> tuple:
        """Return ``(steps, finally_steps)``.

        Accepts a bare step array or
        ``{"steps":[...], "finally":[...]}`` (``cleanup`` alias).
        """
        finally_steps: List[Dict[str, Any]] = []
        if isinstance(script, str):
            try:
                script = json.loads(script)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Script must be valid JSON: {exc.msg}") from exc
        if isinstance(script, Mapping):
            raw_finally = script.get("finally") or script.get("cleanup") or []
            if raw_finally and (
                not isinstance(raw_finally, Sequence)
                or isinstance(raw_finally, (str, bytes, bytearray))
            ):
                raise ValueError("finally/cleanup must be a step array.")
            for index, value in enumerate(raw_finally or []):
                if not isinstance(value, Mapping):
                    raise ValueError(f"finally step {index} must be an object.")
                finally_steps.append(dict(value))
            script = script.get("steps") if "steps" in script else script.get("script")
            if script is None and not finally_steps:
                # bare mapping without steps — treat as single-step? no
                raise ValueError("Script object needs a steps array.")
            if script is None:
                script = []
        if not isinstance(script, Sequence) or isinstance(script, (str, bytes, bytearray)):
            raise ValueError("Script must be a JSON array or an object with a steps array.")
        if len(script) + len(finally_steps) > MAX_STEPS:
            raise ValueError(
                f"Script has {len(script) + len(finally_steps)} steps; maximum is {MAX_STEPS}."
            )
        steps: List[Dict[str, Any]] = []
        for index, value in enumerate(script):
            if not isinstance(value, Mapping):
                raise ValueError(f"Step {index} must be an object.")
            steps.append(dict(value))
        return steps, finally_steps

    def _register_desktop_refs(self, value: Any) -> Any:
        """Stamp short-lived ``eN`` refs on read/observe elements for this script."""
        if not isinstance(value, dict):
            return value
        elements = value.get("elements")
        if not isinstance(elements, list) or not elements:
            # compact_observe uses a11y list
            a11y = value.get("a11y")
            if isinstance(a11y, list) and a11y:
                elements = a11y
            else:
                return value
        pid = value.get("pid") or value.get("focus_pid") or getattr(self.ctrl, "_focus_pid", None)
        window_id = value.get("window_id") or getattr(self.ctrl, "_focus_window_id", None)
        self._desktop_refs = {}
        ref_ids: List[str] = []
        stamped: List[Dict[str, Any]] = []
        for i, el in enumerate(elements[:80]):
            if not isinstance(el, dict):
                continue
            ref = f"e{i}"
            idx = el.get("element_index")
            if idx is None:
                idx = el.get("index")
            if idx is None:
                idx = i
            entry = {
                "ref": ref,
                "element_index": int(idx) if idx is not None else i,
                "name": el.get("name") or el.get("label") or "",
                "role": el.get("role"),
                "pid": int(pid) if pid is not None else None,
                "window_id": int(window_id) if window_id is not None else None,
                "bbox": el.get("bbox"),
            }
            self._desktop_refs[ref] = entry
            el = dict(el)
            el["ref"] = ref
            stamped.append(el)
            ref_ids.append(ref)
        if value.get("elements") is not None:
            value = {**value, "elements": stamped, "refs": ref_ids}
        elif value.get("a11y") is not None:
            value = {**value, "a11y": stamped, "refs": ref_ids}
        return value

    def _resolve_ref(self, step: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        ref = step.get("ref")
        if ref is None:
            return None
        key = str(ref).strip()
        hit = self._desktop_refs.get(key)
        if hit is None and key.isdigit():
            hit = self._desktop_refs.get(f"e{key}")
        return hit

    def _capture_fail_evidence(self, max_side: int = 900, quality: int = 55) -> Optional[Dict[str, Any]]:
        """Compact JPEG of focused window/monitor — no lease required (debug path)."""
        try:
            state = {}
            try:
                state = self.ctrl.window_state(getattr(self.ctrl, "_focus_window_id", None)) or {}
            except Exception:
                state = {}
            rect = None
            if isinstance(state, dict) and state.get("known") and state.get("rect"):
                r = state.get("rect")
                try:
                    if len(r) == 4 and int(r[2]) - int(r[0]) > 20 and int(r[3]) - int(r[1]) > 20:
                        rect = tuple(int(x) for x in r)
                except Exception:
                    rect = None
            image = self.ctrl.perception.capture(monitor=1, region=rect)
            if image is None:
                # Absolute fallback: full primary monitor
                image = self.ctrl.perception.capture(monitor=1, region=None)
            if image is None:
                return {"error": "capture returned None"}
            if max(image.size) > max_side:
                scale = max_side / max(image.size)
                image = image.resize(
                    (max(1, round(image.width * scale)), max(1, round(image.height * scale)))
                )
            stream = io.BytesIO()
            image.convert("RGB").save(stream, format="JPEG", quality=max(40, min(85, quality)))
            b64 = base64.b64encode(stream.getvalue()).decode("ascii")
            # Cap ~180KB base64 for agent contexts
            if len(b64) > 240_000:
                stream = io.BytesIO()
                image = image.resize((max(1, image.width // 2), max(1, image.height // 2)))
                image.convert("RGB").save(stream, format="JPEG", quality=45)
                b64 = base64.b64encode(stream.getvalue()).decode("ascii")
            return {
                "mime_type": "image/jpeg",
                "image_base64": b64,
                "size": list(image.size),
                "window": state if isinstance(state, dict) else {},
            }
        except Exception as exc:
            return {"error": f"{type(exc).__name__}: {exc}"}

    def _run_one(
        self,
        index: int,
        step: Dict[str, Any],
        *,
        default_stop: bool,
        screenshot_on_fail: bool,
        tag: Optional[str] = None,
    ) -> Dict[str, Any]:
        op = str(step.get("op") or "").strip().lower().replace("-", "_")
        step_started = time.perf_counter()
        try:
            # Bound UIA waits only. Playwright browser_* must NOT run under
            # ThreadPoolExecutor — killing the worker leaves sticky asyncio hung.
            if op.startswith("wait") or op in {
                "focus", "smart_focus", "verify", "verify_ui",
                "observe", "compact_observe", "read_ui", "read",
            }:
                value = self._run_step_bounded(
                    op, step, timeout_s=float(step.get("timeout", 14.0))
                )
            else:
                value = self._run_step(op, step)
        except Exception as exc:
            value = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        value = _normalize_result(op, value)
        if op in {"read", "read_ui", "observe", "compact_observe"} and _step_ok(value):
            value = self._register_desktop_refs(value)
        if op == "launch" and _step_ok(value) and value.get("pid"):
            try:
                self._script_launched_pids.append(int(value["pid"]))
            except Exception:
                pass
        ok = _step_ok(value)
        if not ok:
            want_shot = step.get("screenshot_on_fail")
            if want_shot is None:
                want_shot = screenshot_on_fail
            if want_shot:
                evidence = self._capture_fail_evidence()
                if evidence is not None:
                    value = {**value, "fail_screenshot": evidence}
            self._last_error = {
                "ok": False,
                "step": index,
                "op": op,
                "error": value.get("error") or value.get("message") or value.get("missing"),
                "result": {
                    k: value.get(k)
                    for k in (
                        "ok", "error", "message", "missing", "found", "blocked",
                        "denied", "reason", "title", "path",
                    )
                    if k in value
                },
                "ts": time.time(),
            }
        entry = {
            "step": index,
            "op": op,
            "ok": ok,
            "elapsed_ms": round((time.perf_counter() - step_started) * 1000),
            "result": value,
        }
        if tag:
            entry["phase"] = tag
        return entry

    def execute(
        self,
        script: Any,
        stop_on_failure: bool = True,
        auto_release_lease: bool = True,
        screenshot_on_fail: Optional[bool] = None,
    ) -> Dict[str, Any]:
        if screenshot_on_fail is None:
            screenshot_on_fail = allow_screenshot_on_fail_default()
        try:
            steps, finally_steps = self.parse_document(script)
        except ValueError as exc:
            return {"ok": False, "error": str(exc), "steps": []}

        results: List[Dict[str, Any]] = []
        started = time.perf_counter()
        acquired_this_script = False
        released_this_script = False
        self._desktop_refs = {}
        self._script_launched_pids = []
        # Keep held lease across execute() calls unless this script acquired and
        # failed mid-way (auto_release_lease), so agents are not stuck.
        for index, step in enumerate(steps):
            entry = self._run_one(
                index, step, default_stop=stop_on_failure, screenshot_on_fail=screenshot_on_fail
            )
            op = entry["op"]
            ok = entry["ok"]
            if op == "lease_acquire" and ok:
                acquired_this_script = True
            if op in {"lease_release", "lease_force_release"} and ok:
                released_this_script = True
            results.append(entry)
            should_stop = step.get("stop_on_failure", stop_on_failure)
            if should_stop and not ok:
                break

        main_count = len([r for r in results if r.get("phase") != "finally"])
        stopped_early = main_count < len(steps)

        # finally / cleanup always runs (best-effort, never aborts mid-cleanup for one fail).
        finally_results: List[Dict[str, Any]] = []
        for fi, step in enumerate(finally_steps):
            entry = self._run_one(
                main_count + fi,
                step,
                default_stop=False,
                screenshot_on_fail=False,
                tag="finally",
            )
            op = entry["op"]
            if op == "lease_release" and entry["ok"]:
                released_this_script = True
            finally_results.append(entry)
        results.extend(finally_results)

        auto_released = False
        # Only auto-release on failure/early-stop so multi-execute lease handoff
        # still works when a script intentionally ends still holding the lease.
        if (
            auto_release_lease
            and stopped_early
            and acquired_this_script
            and not released_this_script
            and self._script_lease_token
        ):
            try:
                rel = desktop_lease.release(token=self._script_lease_token)
                self._script_lease_token = None
                auto_released = bool(rel.get("ok") and rel.get("released"))
                results.append(
                    {
                        "step": len(results),
                        "op": "lease_release",
                        "ok": auto_released,
                        "elapsed_ms": 0,
                        "auto": True,
                        "result": {**rel, "auto": True},
                    }
                )
            except Exception as exc:
                results.append(
                    {
                        "step": len(results),
                        "op": "lease_release",
                        "ok": False,
                        "elapsed_ms": 0,
                        "auto": True,
                        "result": {
                            "ok": False,
                            "auto": True,
                            "error": f"{type(exc).__name__}: {exc}",
                        },
                    }
                )

        main_ok = not any(
            (not r.get("ok")) and r.get("phase") != "finally" and not r.get("auto")
            for r in results
        )
        return {
            "ok": main_ok,
            "elapsed_ms": round((time.perf_counter() - started) * 1000),
            "completed": main_count,
            "requested": len(steps),
            "stopped_early": stopped_early,
            "auto_released_lease": auto_released,
            "finally_ran": len(finally_results),
            "last_error": self._last_error,
            "steps": results,
        }

    def _lease_token(self, step: Dict[str, Any]) -> Optional[str]:
        token = (
            step.get("lease")
            or step.get("lease_token")
            or step.get("token")
            or self._script_lease_token
        )
        if token is None:
            return None
        return str(token).strip() or None

    def _ensure_lease(self, op: str, step: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        needs = False
        if op.startswith("browser_") or op in LEASE_REQUIRED_OPS:
            needs = True
        if op == "proc":
            action = str(step.get("action") or step.get("mode") or "list").lower()
            needs = action in {"kill", "stop", "terminate"}
        if op == "desktop":
            action = str(step.get("action") or "list").lower()
            needs = action in {"switch", "goto", "set"}
        # Catalog lease-free wins — including browser_act / browser_query HTTP aliases.
        if op in LEASE_FREE_OPS:
            needs = False
        if not needs:
            return None
        token = self._lease_token(step)
        if not token or not desktop_lease.validate(token):
            return _lease_denied()
        return None


    def _is_mutating_op(self, op: str, step: Dict[str, Any]) -> bool:
        if op in {
            "kill_switch", "arm_kill_switch", "disarm_kill_switch",
            "action_log", "log", "recent_actions",
            "lease_acquire", "lease_renew", "lease_release", "lease_status", "lease_force_release",
            "list_cursors", "cursors",
        }:
            return False
        if op in LEASE_FREE_OPS:
            return False
        if op == "proc":
            action = str(step.get("action") or step.get("mode") or "list").lower()
            return action in {"kill", "stop", "terminate"}
        if op == "desktop":
            action = str(step.get("action") or "list").lower()
            return action in {"switch", "goto", "set"}
        if op.startswith("browser_") or op in LEASE_REQUIRED_OPS:
            return True
        return False

    def _step_safety_text(self, op: str, step: Dict[str, Any]) -> str:
        chunks: List[str] = []
        for key in ("text", "query", "command", "path", "exe", "url", "target", "keys", "key", "hotkey"):
            val = step.get(key)
            if val is None:
                continue
            if isinstance(val, (list, tuple)):
                chunks.append(" ".join(str(x) for x in val))
            else:
                chunks.append(str(val))
        fields = step.get("fields")
        if isinstance(fields, Mapping):
            chunks.extend(str(v) for v in fields.values())
            chunks.extend(str(k) for k in fields.keys())
        args = step.get("args")
        if isinstance(args, (list, tuple)):
            chunks.extend(str(a) for a in args)
        elif args:
            chunks.append(str(args))
        return " ".join(chunks)

    def _ensure_safety(self) -> Any:
        ctrl = self.ctrl
        safety = getattr(ctrl, "safety", None)
        if safety is not None:
            return safety
        from exo_control.safety import SafetyGate, SafetyConfig
        from exo_control.config import AetherConfig
        try:
            cfg = AetherConfig.load()
            sc = SafetyConfig(
                max_actions_per_minute=int(cfg.max_actions_per_minute),
                max_clicks_per_minute=int(cfg.max_clicks_per_minute),
            )
        except Exception:
            sc = SafetyConfig()
        safety = SafetyGate(sc)
        try:
            ctrl.safety = safety
        except Exception:
            pass
        return safety

    def _safety_block(self, op: str, step: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if not self._is_mutating_op(op, step):
            return None
        safety = self._ensure_safety()
        kind = "click" if op in {"click", "smart_click", "browser_click"} else "action"
        text = self._step_safety_text(op, step)
        confirm = parse_confirm(step.get("confirm"))
        ok, why = safety.check(kind=kind, text=text, confirm=confirm, record=True)
        if not ok:
            return {"ok": False, "success": False, "error": why, "blocked": True}
        # Prevent double-count when SmartController methods also call safety.check
        try:
            setattr(self.ctrl, "_safety_prechecked", True)
        except Exception:
            pass
        return None

    def _record_action(self, op: str, step: Dict[str, Any], value: Any) -> None:
        if not self._is_mutating_op(op, step):
            return
        ok = True
        if isinstance(value, Mapping):
            if value.get("ok") is False or value.get("success") is False:
                ok = False
        entry = {
            "ts": time.time(),
            "op": op,
            "ok": ok,
            "outcome": "ok" if ok else "fail",
        }
        if isinstance(value, Mapping):
            if value.get("error"):
                entry["error"] = value.get("error")
            if value.get("message"):
                entry["message"] = value.get("message")
        self._action_log.append(entry)
        if len(self._action_log) > 500:
            del self._action_log[: len(self._action_log) - 500]
        log = getattr(self.ctrl, "log", None)
        if log is not None and hasattr(log, "record"):
            try:
                log.record(op, ok=ok, **{k: entry[k] for k in ("error", "message") if k in entry})
            except Exception:
                pass

    def _action_log_tail(self, n: int = 20) -> Dict[str, Any]:
        n = max(1, min(200, int(n)))
        items: List[Dict[str, Any]] = []
        recent = getattr(self.ctrl, "recent_actions", None)
        if callable(recent):
            try:
                items = list(recent(n)) or []
            except Exception:
                items = []
        if not items:
            items = list(self._action_log[-n:])
        return {"ok": True, "count": len(items), "entries": items, "actions": items}


    def _require_focus(self, op: str, step: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Hard-fail click/type/fill/keys/wheel when nothing is focused."""
        if op not in {
            "click", "smart_click", "type", "smart_type", "fill",
            "keys", "press", "hotkey", "smart_hotkey",
            "scroll", "smart_scroll", "scroll_into_view", "into_view", "hover",
        }:
            return None
        ctrl = self.ctrl
        # Explicit title/pid on the step: focus first, fail if it fails.
        if step.get("title") or step.get("pid") is not None:
            mon = step.get("monitor")
            focused = self._smart_focus(
                ctrl,
                title=step.get("title"),
                pid=step.get("pid"),
                monitor=int(mon) if mon is not None else None,
            )
            if not isinstance(focused, dict) or not focused.get("ok"):
                return {
                    "ok": False,
                    "success": False,
                    "error": "act-without-focus: focus failed",
                    "blocked": True,
                    "detail": focused,
                }
            return None
        wid = getattr(ctrl, "_focus_window_id", None)
        pid = getattr(ctrl, "_focus_pid", None)
        if not wid and not pid:
            return {
                "ok": False,
                "success": False,
                "error": "act-without-focus: no focused window",
                "blocked": True,
            }
        return None

    def _smart_focus(
        self,
        ctrl: Any,
        *,
        title: Any = None,
        pid: Any = None,
        monitor: Any = None,
    ) -> Dict[str, Any]:
        """Call controller.smart_focus; tolerate stubs without monitor kw."""
        kwargs: Dict[str, Any] = {}
        if title is not None:
            kwargs["title"] = title
        if pid is not None:
            kwargs["pid"] = pid
        if monitor is not None:
            kwargs["monitor"] = int(monitor)
        try:
            return ctrl.smart_focus(**kwargs)
        except TypeError:
            kwargs.pop("monitor", None)
            return ctrl.smart_focus(**kwargs)

    def _screenshot_window_bind(
        self, title: Any, focused: Mapping[str, Any], state: Mapping[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Fail closed if capture is not bound to the requested title/HWND."""
        want = str(title or "").strip().lower()
        if not want:
            return None
        got = str(focused.get("title") or state.get("title") or "").strip().lower()
        # Fail closed when bind cannot be confirmed (empty actual) or titles diverge.
        if (not got) or (want not in got and got not in want):
            return {
                "ok": False,
                "error": "screenshot wrong-window: title mismatch",
                "requested": title,
                "actual": focused.get("title") or state.get("title"),
            }
        if focused.get("window_id") is not None and state.get("known"):
            # If state carries a window_id/hwnd, require match when present.
            for key in ("window_id", "hwnd"):
                if key in state and state.get(key) is not None:
                    if int(state.get(key)) != int(focused.get("window_id")):
                        return {
                            "ok": False,
                            "error": "screenshot wrong-window: HWND mismatch",
                            "requested": focused.get("window_id"),
                            "actual": state.get(key),
                        }
        return None

    def _screenshot_monitor_bind(
        self,
        monitor_id: int,
        focused: Optional[Mapping[str, Any]],
        state: Mapping[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """Fail closed if a bound window does not live on the requested monitor."""
        from exo_control.monitors import get_monitor, monitor_bind_error, rect_on_monitor

        mon = get_monitor(int(monitor_id))
        if mon is None:
            return monitor_bind_error(int(monitor_id), "unknown monitor id")
        if not focused and not state:
            return None  # monitor-only capture is fine
        rect = None
        if focused and focused.get("rect"):
            rect = focused.get("rect")
        elif state.get("rect"):
            rect = state.get("rect")
        if rect is None:
            # No rect to verify — only fail when title was bound and we cannot confirm.
            if focused and focused.get("ok") is False:
                return monitor_bind_error(int(monitor_id), "focus failed on monitor")
            return None
        if not rect_on_monitor(rect, mon):
            return {
                "ok": False,
                "error": "screenshot wrong-monitor: window not on requested display",
                "monitor": int(monitor_id),
                "rect": rect,
                "monitors": [mon],
            }
        return None

    def _run_step(self, op: str, step: Dict[str, Any]) -> Any:
        ctrl = self.ctrl
        denied = self._ensure_lease(op, step)
        if denied is not None:
            return denied
        blocked = self._safety_block(op, step)
        if blocked is not None:
            self._record_action(op, step, blocked)
            return blocked
        no_focus = self._require_focus(op, step)
        if no_focus is not None:
            self._record_action(op, step, no_focus)
            return no_focus
        try:
            value = self._dispatch_step(op, step)
        finally:
            try:
                setattr(ctrl, "_safety_prechecked", False)
            except Exception:
                pass
        value = self._maybe_compact_result(op, step, value)
        self._record_action(op, step, value)
        value = self._maybe_attach_seen(op, step, value)
        return value

    def _maybe_compact_result(self, op: str, step: Dict[str, Any], value: Any) -> Any:
        """Compact eyes/snapshot payloads unless step.verbose is True."""
        compact_ops = {
            "observe", "compact_observe", "eyes", "eyes_read", "look", "glance",
            "browser_snapshot", "read_ui", "read",
            "search", "search_web", "pplx_search", "web_search",
            "search_content", "search_snippets", "pplx_content",
            "browser_use", "browser_use_task", "browser_use_run",
            "scrape", "firecrawl", "crawl", "site_map",
            "files_convert", "read_doc", "agentql", "browser_query",
            "memory_search", "recall", "screen_search",
        }
        if op not in compact_ops:
            return value
        verbose = step.get("verbose") is True
        if not isinstance(value, (dict, list)):
            return value
        # read_ui: only compact when fat
        if op in {"read_ui", "read"} and isinstance(value, dict):
            try:
                import json as _json
                raw_len = len(_json.dumps(value, default=str))
            except Exception:
                raw_len = MAX_COMPACT_CHARS + 1
            if raw_len <= MAX_COMPACT_CHARS and not value.get("screenshot_base64"):
                if verbose:
                    return value
                # still mark compact for consistency when under cap? Spec: wrap unless verbose.
        return compact_payload(value, verbose=verbose)

    _SEEN_AFTER = frozenset({
        "click", "smart_click", "type", "smart_type", "fill",
        "scroll", "smart_scroll", "scroll_into_view", "into_view", "hover",
        "drag", "smart_drag", "hotkey", "smart_hotkey", "keys", "press",
        "browser_click", "browser_type", "browser_scroll", "browser_scroll_into_view",
        "browser_into_view", "browser_hover", "browser_press", "browser_fill",
        "browser_navigate",
    })

    def _maybe_start_live_eyes(self, step: Dict[str, Any], out: Dict[str, Any]) -> None:
        if step.get("eyes") is False or not live_eyes_enabled():
            return
        ctrl = self.ctrl
        if not hasattr(ctrl, "eyes_start"):
            return
        already = bool(getattr(getattr(ctrl, "_eyes", None), "_running", False))
        try:
            started = ctrl.eyes_start(
                fps=float(step.get("fps", 6.0)),
                ocr_on_change=bool(step.get("ocr_on_change", False)),
            )
            out["eyes"] = started if isinstance(started, dict) else {"ok": True}
            if not already:
                self._eyes_started_by_lease = True
            self._hint_eyes_focus()
        except Exception as exc:
            out["eyes"] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    def _maybe_stop_live_eyes(self, out: Dict[str, Any]) -> None:
        if not self._eyes_started_by_lease:
            return
        ctrl = self.ctrl
        self._eyes_started_by_lease = False
        if not hasattr(ctrl, "eyes_stop"):
            return
        try:
            stopped = ctrl.eyes_stop()
            out["eyes"] = stopped if isinstance(stopped, dict) else {"ok": True, "stopped": True}
        except Exception as exc:
            out["eyes"] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    def _hint_eyes_focus(self, focused: Optional[Mapping[str, Any]] = None) -> None:
        ctrl = self.ctrl
        eyes = getattr(ctrl, "_eyes", None)
        setter = getattr(eyes, "set_focus_hint", None)
        if not callable(setter):
            return
        pid = None
        hwnd = None
        monitor = None
        if focused:
            pid = focused.get("pid")
            hwnd = focused.get("window_id") or focused.get("hwnd")
            monitor = focused.get("monitor")
        setter(
            pid=pid if pid is not None else getattr(ctrl, "_focus_pid", None),
            hwnd=hwnd if hwnd is not None else getattr(ctrl, "_focus_window_id", None),
            monitor=monitor if monitor is not None else getattr(ctrl, "_focus_monitor", None),
        )

    def _maybe_attach_seen(self, op: str, step: Dict[str, Any], value: Any) -> Any:
        if step.get("seen") is False or not live_eyes_enabled():
            return value
        if op not in self._SEEN_AFTER:
            return value
        if not isinstance(value, dict) or not _step_ok(value):
            return value
        ctrl = self.ctrl
        eyes = getattr(ctrl, "_eyes", None)
        if eyes is None or not getattr(eyes, "_running", False):
            return value
        try:
            if hasattr(ctrl, "glance"):
                seen = ctrl.glance(force_ocr=False)
            elif hasattr(ctrl, "eyes_read"):
                seen = ctrl.eyes_read(force_ocr=False)
            else:
                return value
            if isinstance(seen, dict) and seen.get("ok"):
                value = dict(value)
                value["seen"] = seen
        except Exception:
            return value
        return value

    def _browser_click_with_structure_miss(
        self, browser: Any, step: Dict[str, Any]
    ) -> Any:
        """Click once; on no-match (non-verbose) refresh snapshot and retry once."""
        click_kwargs = dict(
            ref=step.get("ref"),
            selector=step.get("selector"),
            x=step.get("x"),
            y=step.get("y"),
            space_id=step.get("space_id"),
            text=step.get("text") or step.get("name") or step.get("query"),
            name=step.get("name"),
            query=step.get("query"),
        )
        result = browser.click(**click_kwargs)
        if step.get("verbose") is True:
            return result
        if not isinstance(result, dict) or result.get("ok") is not False:
            return result
        err = str(result.get("error") or "").lower()
        no_match = (
            "no element" in err
            or "not found" in err
            or "no match" in err
            or "unknown ref" in err
        )
        if not no_match:
            return result
        # Structure-miss path: one fresh compact snapshot, then retry click once.
        snap = browser.snapshot(step.get("space_id"), bool(step.get("include_screenshot", False)))
        if isinstance(snap, dict) and snap.get("ok") is not False:
            elements = snap.get("elements") or snap.get("refs") or []
            if isinstance(elements, list):
                self._last_browser_refs = elements
            snap_compact = compact_payload(snap, verbose=False)
        else:
            snap_compact = snap
        retry = browser.click(**click_kwargs)
        if isinstance(retry, dict):
            retry = dict(retry)
            retry["structure_miss_retry"] = True
            retry["snapshot"] = snap_compact
            if step.get("screenshot_on_miss"):
                try:
                    if hasattr(browser, "screenshot"):
                        shot = browser.screenshot(step.get("space_id"))
                    else:
                        shot = browser.snapshot(step.get("space_id"), True)
                    retry["miss_screenshot"] = shot
                    if isinstance(shot, dict):
                        b64 = shot.get("screenshot_base64")
                        if b64:
                            # Explicit top-level key for proves (not stripped by compact snapshot)
                            retry["screenshot_base64"] = b64
                except Exception as exc:
                    retry["miss_screenshot_error"] = f"{type(exc).__name__}: {exc}"
        return retry

    def _observe_budget(self, step: Dict[str, Any]) -> Dict[str, Any]:
        import statistics
        n = max(1, min(500, int(step.get("n", 50))))
        include_ocr = bool(step.get("include_ocr", False))
        times_ms: List[float] = []
        chars: List[int] = []
        ctrl = self.ctrl
        last = None
        for _ in range(n):
            t0 = time.perf_counter()
            obs = ctrl.compact_observe(include_ocr=include_ocr)
            packed = compact_payload(obs, verbose=False)
            elapsed = (time.perf_counter() - t0) * 1000.0
            times_ms.append(elapsed)
            if isinstance(packed, dict) and "_chars" in packed:
                chars.append(int(packed["_chars"]))
            else:
                try:
                    import json as _json
                    chars.append(len(_json.dumps(packed, default=str)))
                except Exception:
                    chars.append(0)
            last = packed
        times_sorted = sorted(times_ms)
        chars_sorted = sorted(chars)

        def _pct(vals: List[float], p: float) -> float:
            if not vals:
                return 0.0
            idx = min(len(vals) - 1, max(0, int(round((p / 100.0) * (len(vals) - 1)))))
            return round(float(vals[idx]), 3)

        return {
            "ok": True,
            "n": n,
            "include_ocr": include_ocr,
            "p50_ms": _pct(times_sorted, 50),
            "p95_ms": _pct(times_sorted, 95),
            "p95_chars": int(_pct([float(c) for c in chars_sorted], 95)),
            "max_chars": MAX_COMPACT_CHARS,
            "last": last,
        }

    def _dispatch_step(self, op: str, step: Dict[str, Any]) -> Any:
        ctrl = self.ctrl
        if op in {"cursor_exec", "cursor_run"}:
            cid = str(step.get("cursor_id") or step.get("cursor") or "main")
            steps = step.get("steps") or step.get("script") or []
            return ctrl.cursor_exec(cid, steps, stop_on_failure=bool(step.get("stop_on_failure", True)))
        if op in {"create_cursor", "cursor_create"}:
            return ctrl.create_cursor(str(step.get("cursor_id") or step.get("id") or step.get("cursor") or "main"))
        if op in {"list_cursors", "cursors"}:
            return {"ok": True, "cursors": ctrl.list_cursors()}
        if op == "status":
            st = ctrl.status() if hasattr(ctrl, "status") else {"ok": True}
            if isinstance(st, dict):
                st = {**st, **identity()}
                st["ok"] = True
                from exo_control import search_ops
                caps = st.setdefault("capabilities", {})
                if isinstance(caps, dict):
                    caps["search_web"] = True
                    caps["search_configured"] = search_ops.configured()
                    from exo_control import addon_ops, browser_use_ops, ego_ops
                    caps["browser_use"] = True
                    caps["browser_use_configured"] = browser_use_ops.configured()
                    caps["ego_lite"] = False
                    caps["ego_windows_ready"] = False
                    ego = ego_ops.detect()
                    caps["ego_available"] = bool(ego.get("available"))
                    caps.update(addon_ops.capabilities())
            return st
        if op in {"windows", "list_windows"}:
            mon = step.get("monitor")
            if hasattr(ctrl, "list_windows"):
                try:
                    return ctrl.list_windows(
                        monitor=int(mon) if mon is not None else None,
                        as_dict=True,
                    )
                except TypeError:
                    raw = ctrl.list_windows(monitor=int(mon)) if mon is not None else ctrl.list_windows()
                    return _normalize_result(op, raw)
            return {"ok": True, "windows": [], "count": 0}
        if op in {"monitors", "list_monitors"}:
            from exo_control.monitors import list_monitor_dicts
            mons = list_monitor_dicts()
            return {"ok": True, "monitors": mons, "count": len(mons)}
        if op in {"help", "ops", "capabilities", "catalog"}:
            from exo_control.ops_catalog import list_ops
            detail = bool(step.get("detail") or step.get("verbose") or step.get("fields"))
            # capabilities/catalog are the full bar; help/ops stay compact unless asked.
            compact = False if op in {"capabilities", "catalog"} or detail else None
            return list_ops(
                query=step.get("query") or step.get("q") or step.get("filter"),
                detail=detail,
                compact=compact,
            )
        if op in {"focus", "smart_focus"}:
            mon = step.get("monitor")
            focused = self._smart_focus(
                ctrl,
                title=step.get("title"),
                pid=step.get("pid"),
                monitor=int(mon) if mon is not None else None,
            )
            token = self._lease_token(step)
            if token and isinstance(focused, dict) and focused.get("ok"):
                desktop_lease.set_last_focus(
                    token,
                    {"title": focused.get("title"), "pid": focused.get("pid"),
                     "window_id": focused.get("window_id"), "monitor": focused.get("monitor")},
                )
            if isinstance(focused, dict) and focused.get("ok"):
                self._hint_eyes_focus(focused)
            return focused
        if op in {"read", "read_ui"}:
            return ctrl.read_ui(
                force=step.get("force", True),
                interactive_only=step.get("interactive", step.get("interactive_only", False)),
                max_elements=int(step.get("max_elements", 120)),
            )
        if op in {"observe", "compact_observe"}:
            mon = step.get("monitor")
            kwargs = {"include_ocr": bool(step.get("include_ocr", False))}
            if mon is not None:
                kwargs["monitor"] = int(mon)
            return ctrl.compact_observe(**kwargs)
        if op in {"click", "smart_click"}:
            ref_hit = self._resolve_ref(step)
            if ref_hit is not None:
                return _action_result(
                    ctrl.smart_click(
                        query=step.get("query") or ref_hit.get("name"),
                        element_index=ref_hit.get("element_index"),
                        pid=ref_hit.get("pid"),
                        window_id=ref_hit.get("window_id"),
                        label=ref_hit.get("name"),
                        button=step.get("button", "left"),
                        require_change=bool(step.get("require_change", False)),
                    )
                )
            if step.get("ref") is not None:
                return {
                    "ok": False,
                    "error": f"unknown ref: {step.get('ref')!r}",
                    "known_refs": list(self._desktop_refs.keys())[:40],
                }
            return _action_result(
                ctrl.smart_click(
                    query=step.get("query"),
                    x=step.get("x"),
                    y=step.get("y"),
                    button=step.get("button", "left"),
                    require_change=bool(step.get("require_change", False)),
                    element_index=step.get("element_index"),
                    pid=step.get("pid"),
                    window_id=step.get("window_id") or step.get("hwnd"),
                    label=step.get("label"),
                )
            )
        if op in {"type", "smart_type"}:
            ref_hit = self._resolve_ref(step)
            query = step.get("query")
            if ref_hit is not None and not query:
                # Focus the ref control first when typing into a field ref.
                if ref_hit.get("name"):
                    query = ref_hit.get("name")
                elif ref_hit.get("element_index") is not None:
                    ctrl.smart_click(
                        element_index=ref_hit.get("element_index"),
                        pid=ref_hit.get("pid"),
                        window_id=ref_hit.get("window_id"),
                        label=ref_hit.get("name"),
                    )
            _kwargs = dict(
                text=str(step.get("text", "")),
                query=query,
                clear=bool(step.get("clear", False)),
            )
            try:
                _out = ctrl.smart_type(**_kwargs, confirm=bool(step.get("confirm", False)))
            except TypeError:
                _out = ctrl.smart_type(**_kwargs)
            return _action_result(_out)
        if op in {"scroll", "smart_scroll"}:
            kwargs: Dict[str, Any] = {
                "query": step.get("query"),
                "notches": step.get("notches"),
                "direction": step.get("direction") or step.get("dir"),
                "amount": step.get("amount"),
                "bbox": step.get("bbox"),
            }
            if step.get("dy") is not None:
                kwargs["dy"] = int(step["dy"])
            if step.get("dx") is not None:
                kwargs["dx"] = int(step["dx"])
            try:
                return _action_result(ctrl.smart_scroll(**kwargs))
            except TypeError:
                return _action_result(
                    ctrl.smart_scroll(
                        dy=int(step.get("dy", 600)),
                        dx=int(step.get("dx", 0)),
                        query=step.get("query"),
                    )
                )
        if op in {"scroll_into_view", "into_view"}:
            if hasattr(ctrl, "scroll_into_view"):
                return ctrl.scroll_into_view(
                    query=step.get("query") or step.get("text") or step.get("name"),
                    bbox=step.get("bbox"),
                    max_steps=int(step.get("max_steps", 12)),
                )
            return {"ok": False, "error": "scroll_into_view not available"}
        if op == "hover":
            if hasattr(ctrl, "hover"):
                return _action_result(
                    ctrl.hover(query=step.get("query"), x=step.get("x"), y=step.get("y"))
                )
            return {"ok": False, "error": "hover not available"}
        if op in {"drag", "smart_drag"}:
            return _action_result(
                ctrl.smart_drag(
                    start_query=step.get("start_query"),
                    end_query=step.get("end_query"),
                    start=step.get("start"),
                    end=step.get("end"),
                    duration=float(step.get("duration", 0.35)),
                )
            )
        if op in {"hotkey", "smart_hotkey"}:
            return _action_result(ctrl.smart_hotkey(step.get("keys") or []))
        if op == "fill":
            fields = step.get("fields") or {}
            if not fields and step.get("query") is not None and step.get("text") is not None:
                fields = {str(step.get("query")): str(step.get("text"))}
            return ctrl.smart_fill(
                fields=fields,
                submit=step.get("submit"),
                clear=bool(step.get("clear", True)),
            )
        if op in {"wait", "wait_until"}:
            # Composed waits: wait with all=/any= arrays of condition objects.
            if step.get("all") or step.get("any"):
                mode = "all" if step.get("all") else "any"
                return self._wait_compose(step, mode=mode)
            if "seconds" in step:
                seconds = min(MAX_WAIT_SECONDS, max(0.0, float(step["seconds"])))
                time.sleep(seconds)
                return {"ok": True, "slept": seconds}
            return _action_result(
                ctrl.wait_until(
                    query=step.get("query"),
                    text_contains=step.get("text_contains") or step.get("text") or step.get("expect"),
                    timeout=min(MAX_WAIT_SECONDS, float(step.get("timeout", 15.0))),
                    poll=float(step.get("poll", 0.2)),
                )
            )
        if op == "wait_all":
            return self._wait_compose(step, mode="all")
        if op == "wait_any":
            return self._wait_compose(step, mode="any")
        if op in {"last_error", "error", "last_fail"}:
            if self._last_error is None:
                return {"ok": True, "error": None, "message": "no prior failure in this engine"}
            return {"ok": True, **self._last_error, "has_error": True}
        if op == "wait_gone":
            return _action_result(
                ctrl.wait_gone(
                    query=str(step.get("query", "")),
                    timeout=min(MAX_WAIT_SECONDS, float(step.get("timeout", 15.0))),
                )
            )
        if op == "wait_change":
            return _action_result(
                ctrl.wait_change(
                    timeout=min(MAX_WAIT_SECONDS, float(step.get("timeout", 10.0))),
                    poll=float(step.get("poll", 0.35)),
                    threshold=step.get("threshold"),
                    expect=step.get("expect") or step.get("text") or step.get("text_contains") or step.get("query"),
                )
            )
        if op in {"verify", "verify_ui"}:
            expect = step.get("expect")
            if expect is None and step.get("text"):
                expect = step.get("text")
            if isinstance(expect, str):
                expect = [expect]
            gone = step.get("expect_gone", step.get("gone"))
            if isinstance(gone, str):
                gone = [gone]
            return ctrl.verify_ui(
                expect=expect,
                expect_gone=gone,
                timeout=min(MAX_WAIT_SECONDS, float(step.get("timeout", 6.0))),
            )
        if op == "clipboard_get":
            return ctrl.clipboard_get()
        if op == "clipboard_set":
            return ctrl.clipboard_set(str(step.get("text", "")))
        if op == "stats":
            return ctrl.stats(reset=bool(step.get("reset", False)))

        if op in {"browser_use", "browser_use_task", "browser_use_run"}:
            from exo_control import browser_use_ops
            return browser_use_ops.run_task(step)
        if op in {"browser_use_start", "browser_cloud"}:
            from exo_control import browser_use_ops
            out = browser_use_ops.start_browser(step)
            if out.get("ok") and out.get("id"):
                self._browser_use_session = str(out["id"])
            return out
        if op == "browser_use_stop":
            from exo_control import browser_use_ops
            out = browser_use_ops.stop_browser(step, default_id=self._browser_use_session)
            if out.get("ok"):
                self._browser_use_session = None
            return out
        if op in {"ego", "ego_status", "ego_lite"}:
            from exo_control import ego_ops
            return ego_ops.detect()

        from exo_control import addon_ops
        addon = addon_ops.dispatch(op, step)
        if addon is not None:
            return addon

        browser = self._get_browser() if op.startswith("browser_") else None
        if op == "browser_connect":
            return self._browser_connect(browser, step)
        if op == "browser_spaces":
            return browser.list_spaces()
        if op == "browser_create_space":
            return {"ok": True, "space_id": browser.create_space(step.get("name"), url=step.get("url"), external=step.get("external"))}
        if op == "browser_navigate":
            return browser.navigate(
                str(step.get("url", "")), step.get("space_id"), step.get("wait", "domcontentloaded")
            )
        if op == "browser_snapshot":
            snap = browser.snapshot(step.get("space_id"), bool(step.get("include_screenshot", False)))
            if isinstance(snap, dict) and snap.get("ok") is not False:
                elements = snap.get("elements") or snap.get("refs") or []
                if isinstance(elements, list):
                    self._last_browser_refs = elements
            return snap
        if op == "browser_click":
            return self._browser_click_with_structure_miss(browser, step)
        if op == "browser_type":
            return browser.type_text(
                str(step.get("text", "")), step.get("ref"), step.get("selector"),
                bool(step.get("clear", False)), step.get("space_id")
            )
        if op == "browser_press":
            return browser.press(str(step.get("key", "")), step.get("space_id"))
        if op == "browser_scroll":
            kwargs = dict(
                dy=step.get("dy"),
                space_id=step.get("space_id"),
                dx=step.get("dx", 0),
                notches=step.get("notches"),
                direction=step.get("direction") or step.get("dir"),
                amount=step.get("amount"),
                query=step.get("query") or step.get("text") or step.get("name"),
                selector=step.get("selector"),
                ref=step.get("ref"),
            )
            try:
                return browser.scroll(**kwargs)
            except TypeError:
                return browser.scroll(int(step.get("dy", 600)), step.get("space_id"))
        if op in {"browser_scroll_into_view", "browser_into_view"}:
            if hasattr(browser, "scroll_into_view"):
                return browser.scroll_into_view(
                    text=step.get("text") or step.get("query") or step.get("name"),
                    selector=step.get("selector"),
                    ref=step.get("ref"),
                    space_id=step.get("space_id"),
                )
            return {"ok": False, "error": "browser_scroll_into_view not available"}
        if op == "browser_hover":
            if hasattr(browser, "hover"):
                return browser.hover(
                    ref=step.get("ref"),
                    selector=step.get("selector"),
                    text=step.get("text") or step.get("query") or step.get("name"),
                    space_id=step.get("space_id"),
                )
            return {"ok": False, "error": "browser_hover not available"}
        if op == "browser_wait":
            # Op layer uses SECONDS (like wait_change). Playwright wants ms.
            raw_t = float(step.get("timeout", 15))
            timeout_ms = raw_t * 1000.0 if raw_t <= 300 else raw_t  # <=300 => seconds
            timeout_ms = min(60000.0, timeout_ms)
            return browser.wait_for(
                text=step.get("text") or step.get("name") or step.get("query"),
                selector=step.get("selector"),
                timeout=timeout_ms,
                space_id=step.get("space_id"),
                name=step.get("name"),
                query=step.get("query"),
            )
        if op == "browser_fill":
            fields = step.get("fields")
            if not fields:
                needle = step.get("text") or step.get("name") or step.get("query") or step.get("label")
                value = step.get("value")
                if value is None:
                    value = step.get("text_value") or step.get("input")
                if needle is not None and value is not None:
                    fields = {str(needle): str(value)}
                else:
                    return {
                        "ok": False,
                        "error": "browser_fill requires fields{} or text/name + value",
                        "results": [],
                    }
            return browser.fill_form(fields or {}, step.get("space_id"))
        if op == "browser_eval":
            if deny_browser_eval():
                return {"ok": False, "error": "browser_eval denied by EXO_DENY_BROWSER_EVAL=1"}
            if not parse_confirm(step.get("confirm")):
                return {"ok": False, "error": "browser_eval requires confirm=true"}
            return browser.evaluate(str(step.get("js", "")), step.get("space_id"))
        if op == "browser_close_space":
            return browser.close_space(str(step.get("space_id", "")))
        if op in {"browser_network", "browser_har"}:
            if hasattr(browser, "network_log"):
                return browser.network_log(
                    step.get("space_id"),
                    int(step.get("max") or step.get("limit") or 40),
                )
            return {"ok": False, "error": "browser_network not available"}
        if op == "browser_downloads":
            if hasattr(browser, "downloads"):
                return browser.downloads(
                    step.get("space_id"),
                    int(step.get("max") or step.get("limit") or 20),
                )
            return {"ok": False, "error": "browser_downloads not available"}
        if op in {"browser_pdf", "browser_print"}:
            path = str(step.get("path") or step.get("out") or "").strip()
            if not path:
                return {"ok": False, "error": "browser_pdf requires path"}
            ok, resolved, outside = files_ops._resolve_under_roots(path)
            if not ok:
                return {"ok": False, "error": resolved}
            denied = files_ops._outside_denied(
                "browser_pdf", resolved, parse_confirm(step.get("confirm", False)),
            ) if outside else None
            if denied:
                return denied
            if hasattr(browser, "pdf"):
                return browser.pdf(resolved, step.get("space_id"))
            return {"ok": False, "error": "browser_pdf not available"}
        if op in {"browser_tabs", "browser_switch"}:
            if hasattr(browser, "tabs"):
                return browser.tabs(
                    space_id=step.get("space_id"),
                    index=step.get("index"),
                    url=step.get("url") or step.get("href"),
                )
            return {"ok": False, "error": "browser_tabs not available"}
        if op == "browser_back":
            return browser.back(step.get("space_id")) if hasattr(browser, "back") else {"ok": False, "error": "browser_back not available"}
        if op == "browser_forward":
            return browser.forward(step.get("space_id")) if hasattr(browser, "forward") else {"ok": False, "error": "browser_forward not available"}
        if op == "browser_reload":
            return browser.reload(step.get("space_id")) if hasattr(browser, "reload") else {"ok": False, "error": "browser_reload not available"}
        if op == "browser_select":
            sel = str(step.get("selector") or step.get("css") or "")
            if not sel:
                return {"ok": False, "error": "browser_select requires selector"}
            return browser.select(sel, step.get("value") or step.get("option"), step.get("space_id"))
        if op == "browser_upload":
            sel = str(step.get("selector") or step.get("css") or "")
            path = str(step.get("path") or step.get("file") or "")
            if not sel or not path:
                return {"ok": False, "error": "browser_upload requires selector and path"}
            ok, resolved, outside = files_ops._resolve_under_roots(path)
            if not ok:
                return {"ok": False, "error": resolved}
            denied = files_ops._outside_denied(
                "browser_upload", resolved, parse_confirm(step.get("confirm", False)),
            ) if outside else None
            if denied:
                return denied
            return browser.upload(sel, resolved, step.get("space_id"))
        if op == "browser_dialog":
            return browser.page_dialog(
                action=str(step.get("action") or "accept"),
                text=step.get("text") or step.get("prompt"),
                space_id=step.get("space_id"),
            )
        if op == "browser_storage":
            return browser.storage(str(step.get("kind") or step.get("type") or "local"), step.get("space_id"))
        if op == "browser_cookies":
            include = parse_confirm(step.get("confirm", False)) or bool(step.get("include_values"))
            if include and not parse_confirm(step.get("confirm", False)):
                include = False
            return browser.cookies(step.get("space_id"), include_values=include)
        if op == "browser_console":
            return browser.console_log(
                step.get("space_id"),
                int(step.get("max") or step.get("limit") or 40),
            )
        if op == "browser_viewport":
            return browser.viewport(
                width=step.get("width") or step.get("w"),
                height=step.get("height") or step.get("h"),
                space_id=step.get("space_id"),
            )

        if op in {"screenshot", "shot"}:
            # path => write file; otherwise return compact base64 JPEG via engine helper
            out = step.get("path") or step.get("out")
            title = step.get("title")
            mon = step.get("monitor")
            mon_id = int(mon) if mon is not None else 1
            focused = None
            if title:
                focused = self._smart_focus(
                    ctrl,
                    title=str(title),
                    monitor=int(mon) if mon is not None else None,
                )
                if not focused.get("ok"):
                    return focused
            if mon is not None:
                bind_err = self._screenshot_monitor_bind(
                    mon_id, focused, ctrl.window_state(ctrl._focus_window_id) if title else {},
                )
                if bind_err is not None:
                    return bind_err
            if out:
                state = ctrl.window_state(ctrl._focus_window_id)
                if title and focused is not None:
                    mismatch = self._screenshot_window_bind(title, focused, state if isinstance(state, dict) else {})
                    if mismatch is not None:
                        return mismatch
                rect = state.get("rect") if state.get("known") else None
                # Monitor-only shot (no title): bind to full display region.
                if mon is not None and not title:
                    rect = None
                image = ctrl.perception.capture(
                    monitor=mon_id,
                    region=tuple(rect) if rect else None,
                )
                if image is None:
                    return {"ok": False, "error": "Screen capture failed."}
                ok_p, resolved_p, outside_p = files_ops._resolve_under_roots(str(out))
                if not ok_p:
                    return {"ok": False, "error": resolved_p}
                if outside_p:
                    denied_p = files_ops._outside_denied(
                        "screenshot", resolved_p, parse_confirm(step.get("confirm"))
                    )
                    if denied_p is not None:
                        return denied_p
                dest = Path(resolved_p)
                dest.parent.mkdir(parents=True, exist_ok=True)
                image.save(str(dest))
                out = dest
                result = {"ok": True, "path": str(out), "size": list(image.size), "window": state, "monitor": mon_id}
                return result
            # When title is bound, verify via helper after capture metadata
            shot = self.screenshot(
                title=None,
                monitor=mon_id,
                max_side=int(step.get("max_side", 1600)),
                quality=int(step.get("quality", 78)),
                bind_window=bool(title),
            )
            if title and focused is not None and isinstance(shot, dict) and shot.get("ok"):
                mismatch = self._screenshot_window_bind(title, focused, shot.get("window") or {})
                if mismatch is not None:
                    return mismatch
                mon_err = self._screenshot_monitor_bind(mon_id, focused, shot.get("window") or {}) if mon is not None else None
                if mon_err is not None:
                    return mon_err
            if isinstance(shot, dict):
                shot["monitor"] = mon_id
            return shot

        if op in {"cdp", "cdp_discover", "exo_cdp"}:
            from exo_control import exo_bridge
            endpoints = sanitize_cdp_endpoints(
                exo_bridge.discover_cdp_endpoints(
                    extra_ports=[int(step["port"])] if step.get("port") else None
                )
            )
            return {"ok": True, "endpoints": endpoints, "count": len(endpoints)}

        if op in {"wait_cdp", "wait_for_cdp"}:
            return self._wait_cdp(step)

        if op in {"launch", "start", "run"}:
            import os
            import subprocess
            from exo_control.launch_resolve import resolve_launch_target
            raw = step.get("command") or step.get("path") or step.get("exe")
            resolved = resolve_launch_target(
                raw, app=step.get("app"), name=step.get("name"), query=step.get("query"),
            )
            if not resolved.get("ok"):
                return resolved
            command = resolved["command"]
            if is_dangerous_launch(str(command)) and not parse_confirm(step.get("confirm")):
                return {
                    "ok": False,
                    "error": "launch of shell/script host requires confirm=true",
                    "command": str(command),
                }
            args = step.get("args") or []
            if isinstance(args, str):
                args = [args]
            cwd = step.get("cwd") or None
            env = os.environ.copy()
            extra = step.get("env") or {}
            if isinstance(extra, dict) and extra:
                if not parse_confirm(step.get("confirm")):
                    return {"ok": False, "error": "launch env= override requires confirm=true"}
                env.update({str(k): str(v) for k, v in extra.items()})
            cdp_port = step.get("cdp_port") or step.get("port")
            if step.get("wait_cdp") or cdp_port is not None:
                port = int(cdp_port or 9229)
                env["EXO_CDP"] = "1"
                env["EXOOS_CDP"] = "1"
                env["AETHER_CDP"] = "1"
                env["EXO_CDP_PORT"] = str(port)
                env["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"] = (
                    f"--remote-debugging-port={port}"
                )
            creationflags = 0
            if os.name == "nt":
                # CREATE_UNICODE_ENVIRONMENT keeps a custom env map reliable on Windows.
                creationflags |= int(getattr(subprocess, "CREATE_UNICODE_ENVIRONMENT", 0x00000400))
                if not step.get("console"):
                    creationflags |= getattr(subprocess, "DETACHED_PROCESS", 0)
                    creationflags |= getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            out = {"ok": True, "command": str(command), "method": resolved.get("method"), "app": resolved.get("app")}
            if resolved.get("shell") and os.name == "nt":
                import ctypes
                params = " ".join(str(a) for a in args) if args else None
                rc = int(ctypes.windll.shell32.ShellExecuteW(
                    None, "open", str(command), params, cwd, 1,
                ))
                if rc <= 32:
                    return {"ok": False, "error": "ShellExecute failed code=%s" % rc,
                            "command": str(command), "method": resolved.get("method")}
                out["pid"] = None
            else:
                proc = subprocess.Popen(
                    [str(command), *[str(a) for a in args]],
                    cwd=cwd,
                    env=env,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    stdin=subprocess.DEVNULL,
                    creationflags=creationflags,
                )
                out["pid"] = proc.pid
            # Fuzzy launch → ready: wait for window unless caller disables it.
            # Default ON for app/name/query launches; OFF only when wait_ready=false.
            title = step.get("wait_window") or step.get("title_contains") or step.get("title") or step.get("window_title")
            fuzzy_app = bool(step.get("app") or step.get("name") or step.get("query"))
            wait_ready = step.get("wait_ready")
            if wait_ready is None:
                wait_ready = bool(fuzzy_app or title)
            if wait_ready or title:
                from pathlib import Path as _P
                stem = str(
                    resolved.get("matched")
                    or resolved.get("app")
                    or _P(str(command)).stem
                )
                # Prefer explicit title; else matched Start Menu name; else app stem
                title_needle = title if (title and not isinstance(title, bool)) else stem
                ww = {
                    "title_contains": title_needle,
                    "timeout": step.get("timeout", 10.0),
                    "poll": step.get("poll", 0.25),
                }
                if out.get("pid"):
                    ww["pid"] = out["pid"]
                ready = _wait_window(ctrl, ww)
                out["window"] = ready
                if not ready.get("ok") and out.get("pid"):
                    # PID may exist before title is ready; retry title-only once
                    ww.pop("pid", None)
                    ready = _wait_window(ctrl, ww)
                    out["window"] = ready
                if not ready.get("ok"):
                    out["ok"] = False
                    out["error"] = ready.get("error") or "window not ready"
                    return out
                if ready.get("pid") and not out.get("pid"):
                    out["pid"] = ready.get("pid")
                auto_focus = step.get("focus", step.get("auto_focus", True))
                if auto_focus and ready.get("ok"):
                    try:
                        focused = self._smart_focus(
                            ctrl,
                            title=ready.get("title") or title_needle,
                            pid=ready.get("pid") or out.get("pid"),
                        )
                    except Exception as exc:
                        focused = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
                    out["focused"] = focused
                    token = self._lease_token(step)
                    if token and isinstance(focused, dict) and focused.get("ok"):
                        desktop_lease.set_last_focus(
                            token,
                            {
                                "title": focused.get("title"),
                                "pid": focused.get("pid"),
                                "window_id": focused.get("window_id"),
                            },
                        )
            if step.get("wait_cdp"):
                wait_step = {
                    "timeout": step.get("timeout", 15.0),
                    "poll": step.get("poll", 0.25),
                }
                if cdp_port is not None:
                    wait_step["port"] = int(cdp_port)
                cdp = self._wait_cdp(wait_step)
                out["cdp"] = cdp
                out["endpoints"] = cdp.get("endpoints") or []
                out["count"] = cdp.get("count", 0)
                if not cdp.get("ok"):
                    out["ok"] = False
                    out["error"] = cdp.get("error") or "CDP wait failed"
            return out

        if op in {"open", "open_path", "open_url"}:
            import os
            target = step.get("path") or step.get("url") or step.get("target")
            if not target:
                return {"ok": False, "error": "open requires path/url/target"}
            if open_needs_confirm(str(target)) and not parse_confirm(step.get("confirm")):
                return {
                    "ok": False,
                    "error": "open of script/binary requires confirm=true",
                    "target": str(target),
                }
            os.startfile(str(target))  # type: ignore[attr-defined]
            return {"ok": True, "opened": str(target)}

        if op in {
            "window_min", "window_minimize",
            "window_max", "window_maximize",
            "window_restore",
            "window_close",
            "window_move", "window_resize", "window_snap",
            "window", "window_state",
        }:
            if step.get("title"):
                mon = step.get("monitor")
                focused = self._smart_focus(
                    ctrl,
                    title=str(step.get("title")),
                    monitor=int(mon) if mon is not None else None,
                )
                if not focused.get("ok"):
                    return focused
            hwnd = step.get("hwnd") or step.get("window_id")
            hwnd_i = int(hwnd) if hwnd is not None else None
            if op in {"window_min", "window_minimize"}:
                return ctrl.window_min(hwnd_i)
            if op in {"window_max", "window_maximize"}:
                return ctrl.window_max(hwnd_i)
            if op == "window_restore":
                return ctrl.window_restore(hwnd_i)
            if op == "window_close":
                return ctrl.window_close(
                    hwnd_i,
                    discard_unsaved=bool(step.get("discard_unsaved", step.get("discard", True))),
                    wait_gone=float(step.get("wait_gone", step.get("timeout", 2.5))),
                )
            if op in {"window_move", "window_resize", "window_snap"}:
                return ctrl.window_move(
                    hwnd_i,
                    x=step.get("x"),
                    y=step.get("y"),
                    w=step.get("w") or step.get("width"),
                    h=step.get("h") or step.get("height"),
                    snap=step.get("snap") or step.get("edge") or (
                        "left" if op == "window_snap" and step.get("side") else step.get("side")
                    ),
                )
            action = str(step.get("action") or step.get("state") or "state").lower()
            if action in {"minimize", "min"}:
                return ctrl.window_min(hwnd_i)
            if action in {"maximize", "max"}:
                return ctrl.window_max(hwnd_i)
            if action in {"restore", "show"}:
                return ctrl.window_restore(hwnd_i)
            if action in {"close", "quit"}:
                return ctrl.window_close(hwnd_i)
            if action in {"state", "status"}:
                h = ctrl._focus_window_id if hwnd_i is None else hwnd_i
                if h is None:
                    return {"ok": False, "error": "no focused window"}
                return {"ok": True, "window_id": int(h), "window": ctrl.window_state(h)}
            return {"ok": False, "error": f"unknown window action: {action}"}

        if op in {"keys", "press"}:
            # hotkey alias that accepts "keys": "ctrl+l" or list
            keys = step.get("keys") or step.get("key") or step.get("hotkey")
            if isinstance(keys, str):
                keys = [part for part in keys.replace("-", "+").split("+") if part]
            elif not isinstance(keys, list):
                keys = []
            return _action_result(ctrl.smart_hotkey(keys))



        if op == "lease_acquire":
            out = desktop_lease.acquire(
                agent_id=str(step.get("agent") or step.get("agent_id") or ""),
                task=str(step.get("task") or ""),
                ttl_sec=float(step.get("ttl_sec", step.get("ttl", 120))),
            )
            if out.get("ok") and out.get("token"):
                self._script_lease_token = str(out["token"])
                self._maybe_start_live_eyes(step, out)
            return out
        if op == "lease_renew":
            token = self._lease_token(step) or str(step.get("token") or "")
            out = desktop_lease.renew(
                token=token,
                ttl_sec=float(step.get("ttl_sec", step.get("ttl", 120))),
            )
            if out.get("ok") and out.get("token"):
                self._script_lease_token = str(out["token"])
            return out
        if op == "lease_release":
            token = self._lease_token(step) or str(step.get("token") or "")
            out = desktop_lease.release(token=token)
            if out.get("ok") and out.get("released"):
                if self._script_lease_token == token:
                    self._script_lease_token = None
                self._maybe_stop_live_eyes(out)
            return out
        if op == "lease_status":
            return desktop_lease.status()

        if op == "eyes_start":
            if hasattr(ctrl, "eyes_start"):
                return ctrl.eyes_start(
                    fps=float(step.get("fps", 6.0)),
                    ocr_on_change=bool(step.get("ocr_on_change", True)),
                )
            return {"ok": False, "error": "eyes_start not available"}
        if op == "eyes_stop":
            if hasattr(ctrl, "eyes_stop"):
                self._eyes_started_by_lease = False
                return ctrl.eyes_stop()
            return {"ok": False, "error": "eyes_stop not available"}
        if op in {"eyes_read", "look", "glance"}:
            if hasattr(ctrl, "glance"):
                return ctrl.glance(force_ocr=bool(step.get("ocr") or step.get("force_ocr")))
            if hasattr(ctrl, "eyes_read"):
                return ctrl.eyes_read(force_ocr=bool(step.get("ocr") or step.get("force_ocr")))
            return {"ok": False, "error": "eyes_read not available"}

        if op == "eyes":
            observe = ctrl.compact_observe(include_ocr=bool(step.get("include_ocr", False)))
            from exo_control import exo_bridge
            endpoints = sanitize_cdp_endpoints(
                exo_bridge.discover_cdp_endpoints(
                    extra_ports=[int(step["port"])] if step.get("port") else None
                )
            )
            summary = [
                {
                    "endpoint": e.get("endpoint"),
                    "port": e.get("port"),
                    "browser": e.get("browser"),
                    "targets": len(e.get("targets") or []),
                }
                for e in endpoints
            ]
            return {
                "ok": True,
                "observe": observe,
                "cdp": {"endpoints": summary, "count": len(summary)},
                "cdp_count": len(summary),
            }

        if op == "apps":
            return _list_apps(max_items=int(step.get("max", 80)))

        if op == "proc":
            action = str(step.get("action") or step.get("mode") or "list").lower()
            if action in {"list", "ls"}:
                out = _list_procs(max_items=int(step.get("max", 120)))
                if isinstance(out, dict):
                    out = {**out, "action": "list"}
                return out
            if action in {"kill", "stop", "terminate"}:
                if not parse_confirm(step.get("confirm")):
                    return {"ok": False, "error": "proc kill requires confirm=true"}
                pid = step.get("pid")
                name = step.get("name") or step.get("process") or step.get("exe")
                if pid is None and not name:
                    return {"ok": False, "error": "proc kill requires pid or name"}
                out = _kill_proc(
                    int(pid) if pid is not None else None,
                    name=str(name) if name else None,
                )
                if isinstance(out, dict):
                    out = {**out, "action": "kill"}
                return out
            return {"ok": False, "error": f"unknown proc action: {action}"}

        if op == "files_list":
            return files_ops.files_list(
                path=str(step.get("path") or "."),
                max_items=int(step.get("max", step.get("limit", 200))),
                confirm=parse_confirm(step.get("confirm", False)),
            )
        if op == "files_read":
            return files_ops.files_read(
                path=str(step.get("path") or ""),
                max_bytes=int(step.get("max_bytes", step.get("max", 32_000))),
                confirm=parse_confirm(step.get("confirm", False)),
            )
        if op == "files_write":
            return files_ops.files_write(
                path=str(step.get("path") or ""),
                text=str(step.get("text", step.get("content", ""))),
                confirm=parse_confirm(step.get("confirm", False)),
            )
        if op == "files_copy":
            return files_ops.files_copy(
                src=str(step.get("src") or step.get("from") or step.get("source") or step.get("path") or ""),
                dst=str(step.get("dst") or step.get("to") or step.get("dest") or step.get("destination") or ""),
                confirm=parse_confirm(step.get("confirm", False)),
            )
        if op == "files_move":
            return files_ops.files_move(
                src=str(step.get("src") or step.get("from") or step.get("source") or step.get("path") or ""),
                dst=str(step.get("dst") or step.get("to") or step.get("dest") or step.get("destination") or ""),
                confirm=parse_confirm(step.get("confirm", False)),
            )
        if op == "files_delete":
            return files_ops.files_delete(
                path=str(step.get("path") or ""),
                confirm=parse_confirm(step.get("confirm", False)),
                recursive=bool(step.get("recursive", False)),
            )
        if op == "registry_read":
            return registry_ops.registry_read(
                path=str(step.get("path") or step.get("key") or ""),
                max_values=int(step.get("max", step.get("max_values", 40))),
            )
        if op == "registry_write":
            return registry_ops.registry_write(
                path=str(step.get("path") or step.get("key") or ""),
                name=str(step.get("name") or step.get("value_name") or ""),
                value=step.get("value"),
                value_type=str(step.get("type") or step.get("value_type") or "string"),
                confirm=parse_confirm(step.get("confirm", False)),
            )
        if op == "proc_list":
            return infra_ops.proc_list(max_items=int(step.get("max", 120)))
        if op == "proc_kill":
            if not parse_confirm(step.get("confirm")):
                return {"ok": False, "error": "proc kill requires confirm=true"}
            pid = step.get("pid")
            name = step.get("name") or step.get("process") or step.get("exe")
            if pid is None and not name:
                return {"ok": False, "error": "proc kill requires pid or name"}
            return infra_ops.kill_proc(
                int(pid) if pid is not None else None,
                name=str(name) if name else None,
                confirm=True,
            )
        if op == "service_list":
            return infra_ops.service_list(max_items=int(step.get("max", 80)))
        if op == "service_status":
            return infra_ops.service_status(str(step.get("name") or step.get("service") or ""))
        if op == "service_control":
            return infra_ops.service_control(
                name=str(step.get("name") or step.get("service") or ""),
                action=str(step.get("action") or step.get("mode") or ""),
                confirm=parse_confirm(step.get("confirm", False)),
            )
        if op == "env_get":
            return infra_ops.env_get(step.get("name") or step.get("var"))
        if op == "env_list":
            return infra_ops.env_list(max_items=int(step.get("max", 200)))
        if op == "tasks_list":
            return infra_ops.tasks_list(max_items=int(step.get("max", 40)))
        if op == "startup_list":
            return infra_ops.startup_list(max_items=int(step.get("max", 80)))
        if op == "observe_budget":
            return self._observe_budget(step)

        if op == "clipboard_image_save":
            out_path = step.get("path") or step.get("out")
            if not out_path:
                return {"ok": False, "error": "clipboard_image_save requires path"}
            return _clipboard_image_save(str(out_path))

        if op in {"clipboard_image_set", "clipboard_set_image"}:
            img_path = step.get("path") or step.get("image") or step.get("file")
            if not img_path:
                return {"ok": False, "error": "clipboard_image_set requires path"}
            from exo_control.clipboard import set_clipboard_image
            return set_clipboard_image(str(img_path))

        if op == "wait_window":
            return _wait_window(ctrl, step)

        if op == "desktop":
            return _desktop_op(step)

        if op == "notify":
            title = str(step.get("title") or "Exo Control")
            body = str(step.get("body") or step.get("message") or step.get("text") or "")
            # LIVE default is a real toast. Stub ONLY when the step explicitly sets stub:true.
            # AETHER_NOTIFY_STUB is ignored here so a leftover process env cannot fake "done".
            if step.get("stub") is True:
                return {"ok": True, "stub": True, "title": title, "body": body, "queued": True}
            out = _notify_toast(title, body)
            if isinstance(out, dict):
                out["stub"] = False
            return out

        
        if op == "lease_force_release":
            token = self._lease_token(step) or str(step.get("token") or "") or None
            agent = step.get("agent") or step.get("agent_id")
            out = desktop_lease.force_release(token=token, agent_id=str(agent) if agent else None)
            if out.get("ok") and out.get("released"):
                if token and self._script_lease_token == str(token):
                    self._script_lease_token = None
                elif not token:
                    self._script_lease_token = None
                self._maybe_stop_live_eyes(out)
            return out

        if op in {"kill_switch", "arm_kill_switch", "disarm_kill_switch"}:
            safety = self._ensure_safety()
            if op == "arm_kill_switch":
                armed = True
            elif op == "disarm_kill_switch":
                armed = False
            else:
                if "armed" in step:
                    armed = bool(step.get("armed"))
                elif "enable" in step:
                    armed = bool(step.get("enable"))
                else:
                    armed = True
            if armed:
                safety.arm_kill_switch()
            else:
                safety.disarm_kill_switch()
            knobs = getattr(ctrl, "kill_switch", None)
            if callable(knobs):
                try:
                    knobs(armed=armed)
                except Exception:
                    pass
            return {"ok": True, "kill_switch": bool(safety.config.kill_switch), "armed": bool(safety.config.kill_switch)}

        if op in {"action_log", "log", "recent_actions"}:
            return self._action_log_tail(n=int(step.get("n") or step.get("limit") or step.get("last") or 20))

        if op in {"search", "search_web", "pplx_search", "web_search"}:
            from exo_control import search_ops
            return search_ops.search_web(step)
        if op in {"search_content", "search_snippets", "pplx_content"}:
            from exo_control import search_ops
            return search_ops.search_content(step)

        return {"ok": False, "error": f"Unknown operation: {op or '<empty>'}"}



    def _run_step_bounded(self, op: str, step: Dict[str, Any], timeout_s: float = 14.0) -> Dict[str, Any]:
        """Wall-clock cap so dead HWND/UIA cannot hang execute >=15s."""
        import concurrent.futures
        timeout_s = max(0.5, min(MAX_WAIT_SECONDS, float(timeout_s)))
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            fut = pool.submit(self._run_step, op, step)
            try:
                return fut.result(timeout=timeout_s)
            except concurrent.futures.TimeoutError:
                return {
                    "ok": False,
                    "error": "step timed out after %.1fs (target may be dead)" % timeout_s,
                    "timeout": timeout_s,
                    "crashed": True,
                }

    def _browser_connect(self, browser: Any, step: Dict[str, Any]) -> Dict[str, Any]:
        provider = str(step.get("provider") or step.get("backend") or "").strip().lower().replace("-", "_")
        page_url = step.get("page_url") or step.get("url_contains")
        page_title = step.get("page_title") or step.get("title")
        endpoint = step.get("cdp_url") or step.get("endpoint") or step.get("url")
        if provider in {"browser_use", "cloud"}:
            from exo_control import browser_use_ops
            started = browser_use_ops.start_browser(step)
            if not started.get("ok"):
                return started
            if started.get("id"):
                self._browser_use_session = str(started["id"])
            endpoint = started.get("cdp_url")
            if not endpoint:
                return {**started, "ok": False, "error": "browser-use session has no cdp_url"}
            attached = browser.connect_cdp(str(endpoint), page_url=page_url, page_title=page_title)
            if isinstance(attached, dict):
                return {
                    **started,
                    **attached,
                    "provider": "browser-use",
                    "browser_id": started.get("id"),
                }
            return attached
        if endpoint is None:
            port = step.get("port")
            endpoint = f"http://127.0.0.1:{int(port)}" if port is not None else "http://127.0.0.1:9222"
        return browser.connect_cdp(str(endpoint), page_url=page_url, page_title=page_title)

    def _wait_cdp(self, step: Dict[str, Any]) -> Dict[str, Any]:
        """Poll discover_cdp_endpoints until count>0 or timeout (default 15s)."""
        from exo_control import exo_bridge

        timeout = min(MAX_WAIT_SECONDS, max(0.0, float(step.get("timeout", 15.0))))
        poll = max(0.05, float(step.get("poll", 0.25)))
        port = step.get("port") or step.get("cdp_port")
        extra_ports = [int(port)] if port is not None else None
        started = time.perf_counter()
        endpoints: List[Dict[str, Any]] = []
        while True:
            endpoints = exo_bridge.discover_cdp_endpoints(extra_ports=extra_ports)
            if endpoints:
                clean = sanitize_cdp_endpoints(endpoints)
                return {
                    "ok": True,
                    "endpoints": clean,
                    "count": len(clean),
                    "waited": round(time.perf_counter() - started, 3),
                }
            if (time.perf_counter() - started) >= timeout:
                return {
                    "ok": False,
                    "error": f"CDP endpoint not found within {timeout}s",
                    "endpoints": [],
                    "count": 0,
                    "timeout": timeout,
                    "waited": round(time.perf_counter() - started, 3),
                }
            time.sleep(min(poll, max(0.0, timeout - (time.perf_counter() - started))))

    def _wait_one_condition(self, cond: Dict[str, Any], timeout: float, poll: float) -> Dict[str, Any]:
        """Evaluate a single wait condition dict."""
        ctrl = self.ctrl
        if "seconds" in cond:
            time.sleep(min(MAX_WAIT_SECONDS, max(0.0, float(cond["seconds"]))))
            return {"ok": True, "slept": float(cond["seconds"])}
        if cond.get("gone") or cond.get("expect_gone") or cond.get("query_gone"):
            q = cond.get("gone") or cond.get("expect_gone") or cond.get("query_gone") or cond.get("query")
            return _action_result(
                ctrl.wait_gone(query=str(q or ""), timeout=timeout)
            )
        if cond.get("window") or cond.get("title") and cond.get("wait_window"):
            return _wait_window(ctrl, {
                "title": cond.get("window") or cond.get("title"),
                "pid": cond.get("pid"),
                "timeout": timeout,
            })
        if cond.get("title") and not cond.get("text") and not cond.get("query") and not cond.get("expect"):
            return _wait_window(ctrl, {"title": cond.get("title"), "pid": cond.get("pid"), "timeout": timeout})
        expect = cond.get("expect") or cond.get("text") or cond.get("text_contains")
        if expect and not cond.get("query"):
            return ctrl.verify_ui(
                expect=expect if isinstance(expect, list) else [expect],
                timeout=timeout,
            )
        return _action_result(
            ctrl.wait_until(
                query=cond.get("query"),
                text_contains=cond.get("text_contains") or cond.get("text") or cond.get("expect"),
                timeout=timeout,
                poll=poll,
            )
        )

    def _wait_compose(self, step: Dict[str, Any], mode: str = "all") -> Dict[str, Any]:
        """Wait until all or any of a list of conditions succeed."""
        raw = step.get(mode) or step.get("conditions") or step.get("waits") or []
        if isinstance(raw, Mapping):
            raw = [raw]
        if not isinstance(raw, list) or not raw:
            return {"ok": False, "error": f"wait_{mode} requires a non-empty conditions array"}
        timeout = min(MAX_WAIT_SECONDS, float(step.get("timeout", 15.0)))
        poll = float(step.get("poll", 0.25))
        deadline = time.time() + timeout
        results: List[Dict[str, Any]] = []
        while time.time() < deadline:
            results = []
            any_ok = False
            all_ok = True
            remaining = max(0.05, deadline - time.time())
            per = remaining if mode == "any" else max(0.15, remaining / max(1, len(raw)))
            for cond in raw:
                if not isinstance(cond, Mapping):
                    results.append({"ok": False, "error": "condition must be object"})
                    all_ok = False
                    continue
                r = self._wait_one_condition(dict(cond), timeout=min(per, 2.0), poll=poll)
                r = _normalize_result("wait", r)
                results.append(r)
                if _step_ok(r):
                    any_ok = True
                else:
                    all_ok = False
            if mode == "all" and all_ok:
                return {"ok": True, "mode": "all", "results": results, "count": len(results)}
            if mode == "any" and any_ok:
                return {"ok": True, "mode": "any", "results": results, "count": len(results)}
            time.sleep(poll)
        return {
            "ok": False,
            "mode": mode,
            "error": f"wait_{mode} timed out",
            "results": results,
            "count": len(results),
        }

    def screenshot_checked(
        self,
        title: Optional[str] = None,
        monitor: int = 1,
        max_side: int = 1600,
        quality: int = 78,
        bind_window: bool = True,
    ) -> Dict[str, Any]:
        """MCP/CLI screenshot — same lease gate as the screenshot op."""
        denied = self._ensure_lease("screenshot", {})
        if denied is not None:
            return {**denied, "hint": "lease_acquire before exo_screenshot"}
        return self.screenshot(
            title=title, monitor=monitor, max_side=max_side,
            quality=quality, bind_window=bind_window,
        )

    def screenshot(
        self,
        title: Optional[str] = None,
        monitor: int = 1,
        max_side: int = 1600,
        quality: int = 78,
        bind_window: bool = True,
    ) -> Dict[str, Any]:
        focused = None
        if title:
            focused = self._smart_focus(self.ctrl, title=title, monitor=monitor)
            if not focused.get("ok"):
                return focused
            mon_err = self._screenshot_monitor_bind(monitor, focused, {})
            if mon_err is not None:
                return mon_err
        state = self.ctrl.window_state(self.ctrl._focus_window_id)
        rect = state.get("rect") if (bind_window and state.get("known")) else None
        if title and focused is not None:
            mon_err = self._screenshot_monitor_bind(
                monitor, focused, state if isinstance(state, dict) else {}
            )
            if mon_err is not None:
                return mon_err
        image = self.ctrl.perception.capture(
            monitor=monitor, region=tuple(rect) if rect else None
        )
        if image is None:
            return {"ok": False, "error": "Screen capture failed."}
        if max(image.size) > max_side:
            scale = max_side / max(image.size)
            image = image.resize(
                (max(1, round(image.width * scale)), max(1, round(image.height * scale)))
            )
        stream = io.BytesIO()
        image.convert("RGB").save(stream, format="JPEG", quality=max(40, min(92, quality)))
        return {
            "ok": True,
            "mime_type": "image/jpeg",
            "image_base64": base64.b64encode(stream.getvalue()).decode("ascii"),
            "size": list(image.size),
            "window": state,
            "monitor": int(monitor),
        }


def _list_running_apps(max_apps: int = 80) -> List[Dict[str, Any]]:
    """Return a plain list of {pid,title,exe,hwnd} (monkeypatch target for tests)."""
    result = _list_apps_impl(max_items=max_apps)
    if isinstance(result, dict):
        return list(result.get("apps") or [])
    return []


def _list_apps(max_items: int = 80) -> Dict[str, Any]:
    apps = _list_running_apps(max_apps=max_items)
    return {"ok": True, "apps": apps, "count": len(apps)}


def _list_apps_impl(max_items: int = 80) -> Dict[str, Any]:
    """Best-effort running apps with pid/title/exe (Windows)."""
    import os
    if os.name != "nt":
        return {"ok": True, "apps": [], "note": "apps op is Windows-only"}
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        apps = []
        seen = set()

        @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
        def _enum(hwnd, _lparam):
            if len(apps) >= max_items:
                return False
            if not user32.IsWindowVisible(hwnd):
                return True
            length = user32.GetWindowTextLengthW(hwnd)
            if length <= 0:
                return True
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            title = buf.value.strip()
            if not title:
                return True
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value in seen:
                return True
            seen.add(pid.value)
            exe = ""
            try:
                PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
                h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
                if h:
                    try:
                        size = wintypes.DWORD(260)
                        ebuf = ctypes.create_unicode_buffer(260)
                        if kernel32.QueryFullProcessImageNameW(h, 0, ebuf, ctypes.byref(size)):
                            exe = ebuf.value
                    finally:
                        kernel32.CloseHandle(h)
            except Exception:
                pass
            apps.append({"pid": int(pid.value), "title": title, "exe": exe, "hwnd": int(hwnd)})
            return True

        user32.EnumWindows(_enum, 0)
        return {"ok": True, "apps": apps, "count": len(apps)}
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def _list_procs(max_items: int = 120) -> Dict[str, Any]:
    import os
    import subprocess
    if os.name != "nt":
        return {"ok": True, "procs": [], "note": "proc list is Windows-oriented"}
    try:
        # Use tasklist CSV — no shell inject of agent input
        completed = subprocess.run(
            ["tasklist", "/FO", "CSV", "/NH"],
            capture_output=True, text=True, timeout=10, check=False,
        )
        rows = []
        import csv
        import io as _io
        reader = csv.reader(_io.StringIO(completed.stdout or ""))
        for row in reader:
            if len(row) < 2:
                continue
            name, pid_s = row[0], row[1]
            try:
                pid = int(pid_s)
            except ValueError:
                continue
            rows.append({"pid": pid, "name": name})
            if len(rows) >= max_items:
                break
        return {"ok": True, "procs": rows, "count": len(rows)}
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def _kill_proc(pid: Optional[int] = None, name: Optional[str] = None) -> Dict[str, Any]:
    """Kill helper used by proc action=kill; hard-denies protected anti-cheat names."""
    return infra_ops.kill_proc(
        int(pid) if pid is not None else None,
        name=name,
        confirm=True,
    )


def _files_list(path: str, max_items: int = 200, confirm: bool = True) -> Dict[str, Any]:
    """Backward-compatible helper; default confirm=True so legacy callers keep working."""
    return files_ops.files_list(path=path, max_items=max_items, confirm=confirm)


def _clipboard_image_save(path: str) -> Dict[str, Any]:
    out = Path(path)
    try:
        from PIL import ImageGrab
        img = ImageGrab.grabclipboard()
        if img is None:
            return {"ok": False, "error": "clipboard has no image"}
        if isinstance(img, list):
            return {"ok": False, "error": "clipboard has file list, not image"}
        out.parent.mkdir(parents=True, exist_ok=True)
        img.save(str(out))
        return {"ok": True, "path": str(out), "size": list(img.size)}
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def _notify_toast(title: str, body: str) -> Dict[str, Any]:
    """Show a real Windows toast/balloon (BurntToast → WinRT → NotifyIcon)."""
    import os
    import subprocess
    if os.name != "nt":
        return {"ok": False, "error": "notify is Windows-only"}

    def _esc_xml(s: str) -> str:
        return (
            s.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&apos;")
        )

    t_ps = title.replace("'", "''")
    b_ps = body.replace("'", "''")
    t_xml = _esc_xml(title)
    b_xml = _esc_xml(body)
    creationflags = int(getattr(subprocess, "CREATE_NO_WINDOW", 0))

    burnt = (
        "if (Get-Module -ListAvailable -Name BurntToast) { "
        f"New-BurntToastNotification -Text '{t_ps}', '{b_ps}'; Write-Output 'burnttoast' "
        "} else { exit 2 }"
    )
    winrt = (
        "[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, "
        "ContentType = WindowsRuntime] | Out-Null; "
        "[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, "
        "ContentType = WindowsRuntime] | Out-Null; "
        "$template = @'\n"
        "<toast><visual><binding template=\"ToastGeneric\">"
        f"<text>{t_xml}</text><text>{b_xml}</text>"
        "</binding></visual></toast>\n"
        "'@; "
        "$xml = New-Object Windows.Data.Xml.Dom.XmlDocument; $xml.LoadXml($template); "
        "$toast = [Windows.UI.Notifications.ToastNotification]::new($xml); "
        "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('Exo Control').Show($toast); "
        "Write-Output 'winrt'"
    )
    balloon = (
        "Add-Type -AssemblyName System.Windows.Forms; "
        "Add-Type -AssemblyName System.Drawing; "
        "$n = New-Object System.Windows.Forms.NotifyIcon; "
        "$n.Icon = [System.Drawing.SystemIcons]::Information; "
        "$n.Visible = $true; "
        f"$n.ShowBalloonTip(4000, '{t_ps}', '{b_ps}', "
        "[System.Windows.Forms.ToolTipIcon]::Info); "
        "Start-Sleep -Seconds 2; $n.Dispose(); Write-Output 'notifyicon'"
    )

    last_err = None
    for method, ps in (("burnttoast", burnt), ("winrt", winrt), ("notifyicon", balloon)):
        try:
            proc = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
                capture_output=True, text=True, timeout=30, creationflags=creationflags,
            )
            out = (proc.stdout or "").strip()
            if proc.returncode == 0 and method in out:
                return {"ok": True, "title": title, "body": body, "queued": True, "method": method}
            last_err = (proc.stderr or proc.stdout or f"exit {proc.returncode}").strip()
        except Exception as exc:
            last_err = f"{type(exc).__name__}: {exc}"
    return {"ok": False, "error": last_err or "notify failed"}


def _wait_window(ctrl: Any, step: Dict[str, Any]) -> Dict[str, Any]:
    """Poll until a window matching title substring and/or pid appears."""
    import time as _time
    title = step.get("title_contains") or step.get("title") or step.get("name") or step.get("query")
    pid = step.get("pid")
    timeout = min(MAX_WAIT_SECONDS, float(step.get("timeout", 15.0)))
    poll = max(0.05, float(step.get("poll", 0.25)))
    if title is None and pid is None:
        return {"ok": False, "error": "wait_window requires title or pid"}
    t0 = _time.time()
    needle = str(title).lower() if title is not None else None
    want_pid = None
    if pid is not None:
        try:
            want_pid = int(pid)
        except Exception:
            return {"ok": False, "error": "pid must be int"}
    last_windows: List[Dict[str, Any]] = []
    while _time.time() - t0 < timeout:
        try:
            windows = ctrl.list_windows() if hasattr(ctrl, "list_windows") else []
        except Exception:
            windows = []
        last_windows = windows if isinstance(windows, list) else []
        for w in last_windows:
            wpid = w.get("pid") or w.get("process_id")
            try:
                wpid_i = int(wpid) if wpid is not None else None
            except Exception:
                wpid_i = None
            wt = str(w.get("title") or w.get("name") or "").lower()
            pid_ok = want_pid is None or wpid_i == want_pid
            title_ok = needle is None or (needle in wt)
            if pid_ok and title_ok:
                return {
                    "ok": True,
                    "title": w.get("title") or w.get("name"),
                    "pid": wpid_i,
                    "window_id": w.get("window_id") or w.get("handle"),
                    "elapsed": round(_time.time() - t0, 3),
                }
        _time.sleep(poll)
    return {
        "ok": False,
        "error": "window not found",
        "title": title,
        "pid": want_pid,
        "elapsed": round(_time.time() - t0, 3),
        "windows": last_windows[:12],
    }


def _desktop_op(step: Dict[str, Any]) -> Dict[str, Any]:
    """Virtual desktop list/switch — best-effort via optional pyvda."""
    action = str(step.get("action") or "list").lower()
    try:
        import pyvda  # type: ignore
    except Exception:
        return {"ok": False, "error": "unsupported", "detail": "pyvda not installed"}
    try:
        desktops = list(pyvda.get_virtual_desktops())
        current = pyvda.current_virtual_desktop()
        if action == "list":
            return {
                "ok": True,
                "action": "list",
                "current": getattr(current, "number", None),
                "desktops": [
                    {"number": getattr(d, "number", i + 1), "name": str(getattr(d, "name", "") or "")}
                    for i, d in enumerate(desktops)
                ],
            }
        if action in {"switch", "goto", "set"}:
            target = step.get("number") or step.get("index") or step.get("desktop")
            if target is None:
                return {"ok": False, "error": "desktop switch requires number"}
            num = int(target)
            for d in desktops:
                if int(getattr(d, "number", -1)) == num:
                    d.go()
                    return {"ok": True, "action": "switch", "number": num}
            if 1 <= num <= len(desktops):
                desktops[num - 1].go()
                return {"ok": True, "action": "switch", "number": num}
            return {"ok": False, "error": f"desktop {num} not found"}
        return {"ok": False, "error": f"unknown desktop action: {action}"}
    except Exception as exc:
        return {"ok": False, "error": "unsupported", "detail": str(exc)}

# Compat alias (v1.x): prefer ExoExecEngine
AetherExecEngine = ExoExecEngine

