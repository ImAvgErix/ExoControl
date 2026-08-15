"""Live seat — hold the desk like remote access, then drive raw HID.

``session_open`` takes the chair (lease + eyes) and keeps it across exec calls.
``pointer`` / ``mouse`` / ``keypress`` / ``drive`` skip UIA and inject the real
cursor and keys. This is not an RDP/VNC pixel stream.
"""
from __future__ import annotations

import sys
import time
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

DEFAULT_TTL_SEC = 1800.0
MAX_DRIVE_EVENTS = 64

SESSION_OPEN = frozenset({"session_open", "seat", "take_seat"})
SESSION_CLOSE = frozenset({"session_close", "leave_seat", "session_end"})
SESSION_STATUS = frozenset({"session_status", "seat_status"})
SESSION_HANDS = frozenset({"pointer", "mouse", "keypress", "drive"})
SESSION_OPS = SESSION_OPEN | SESSION_CLOSE | SESSION_STATUS | SESSION_HANDS

_IMPL: Optional[Callable[[str, Dict[str, Any]], Dict[str, Any]]] = None


class LiveSeat:
    """In-process 'someone is at this desk' flag. Token stays on the engine."""

    def __init__(self) -> None:
        self.seated = False
        self.holder = ""
        self.task = ""
        self.ttl_sec = DEFAULT_TTL_SEC

    def sit(self, holder: str, task: str, ttl_sec: float) -> None:
        self.seated = True
        self.holder = str(holder or "")
        self.task = str(task or "")
        self.ttl_sec = float(ttl_sec) if ttl_sec else DEFAULT_TTL_SEC

    def clear(self) -> None:
        self.seated = False
        self.holder = ""
        self.task = ""


def expires_in_sec(expires_at: Any) -> Optional[float]:
    if not expires_at:
        return None
    try:
        ts = datetime.fromisoformat(str(expires_at).replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return None
    return round(max(0.0, ts - time.time()), 1)


def _no_secret(raw: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(raw)
    out.pop("token", None)
    return out


def public_error(raw: Dict[str, Any]) -> Dict[str, Any]:
    out = _no_secret(raw)
    out["ok"] = False
    out.setdefault("seated", False)
    return out


def public_status(lease: Optional[Dict[str, Any]] = None, *, seated: bool = False) -> Dict[str, Any]:
    lease = _no_secret(lease or {})
    held = bool(lease.get("held"))
    out: Dict[str, Any] = {
        "ok": True,
        "seated": bool(seated and held),
        "held": held,
    }
    if held:
        holder = lease.get("holder") or lease.get("agent_id")
        out["holder"] = holder
        out["agent_id"] = holder
        out["task"] = lease.get("task")
        if lease.get("expires_at"):
            out["expires_at"] = lease.get("expires_at")
            eta = expires_in_sec(lease.get("expires_at"))
            if eta is not None:
                out["expires_in_sec"] = eta
        return out
    if lease.get("expired"):
        out["expired"] = True
        if lease.get("last_holder"):
            out["last_holder"] = lease.get("last_holder")
        if lease.get("task"):
            out["task"] = lease.get("task")
    return out


def _int_xy(raw_x: Any, raw_y: Any) -> Tuple[Optional[Tuple[int, int]], Optional[str]]:
    if raw_x is None or raw_y is None:
        return None, "x and y are required together"
    try:
        return (int(raw_x), int(raw_y)), None
    except (TypeError, ValueError):
        return None, "x and y must be integers"


def _coords(step: Dict[str, Any]) -> Tuple[Optional[Tuple[int, int]], Optional[str]]:
    if "x" in step or "y" in step:
        if step.get("x") is None or step.get("y") is None:
            return None, "x and y are required together"
        return _int_xy(step.get("x"), step.get("y"))
    for key in ("move", "pos", "point", "xy"):
        pair = step.get(key)
        if isinstance(pair, (list, tuple)) and len(pair) >= 2:
            return _int_xy(pair[0], pair[1])
    return None, None


def hid(kind: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    data = dict(payload or {})
    if _IMPL is not None:
        out = _IMPL(kind, data)
        return out if isinstance(out, dict) else {"ok": True, "kind": kind}
    if sys.platform != "win32":
        return {"ok": False, "error": f"{kind} is Windows-only", "code": "WINDOWS_ONLY"}
    return _hid_win(kind, data)


def _hid_win(kind: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    from exo_control.synthetic import inject_win as inj

    kind = str(kind or "").strip().lower()
    if kind == "move":
        x, y = int(payload["x"]), int(payload["y"])
        mover = inj.move_human if payload.get("human", True) else inj.move_abs
        ok = bool(mover(x, y))
        return {"ok": ok, "kind": "move", "x": x, "y": y, "error": None if ok else "move failed"}
    if kind == "pos":
        pos = inj.cursor_pos()
        if not pos:
            return {"ok": False, "error": "cursor position unavailable", "code": "WINDOWS_ONLY"}
        return {"ok": True, "kind": "pos", "x": int(pos[0]), "y": int(pos[1])}
    if kind in {"click", "down", "up"}:
        button = str(payload.get("button") or "left").lower()
        if payload.get("x") is not None and payload.get("y") is not None:
            moved = hid("move", {"x": payload["x"], "y": payload["y"], "human": payload.get("human", False)})
            if not moved.get("ok"):
                return moved
        ok = bool(inj.mouse_button(button, kind))
        return {"ok": ok, "kind": kind, "button": button, "error": None if ok else f"{kind} failed"}
    if kind == "key":
        name = str(payload.get("key") or payload.get("name") or "").strip()
        action = str(payload.get("action") or "tap").lower()
        if not name:
            return {"ok": False, "error": "key required"}
        ok = bool(inj.key_event(name, action))
        return {"ok": ok, "kind": "key", "key": name, "action": action, "error": None if ok else "key failed"}
    if kind == "type":
        text = str(payload.get("text") or "")
        ok = bool(inj.type_unicode(text)) if text else True
        return {"ok": ok, "kind": "type", "n": len(text), "error": None if ok else "type failed"}
    if kind == "wheel":
        notches = int(payload.get("notches") or payload.get("wheel") or 0)
        h_notches = int(payload.get("h_notches") or payload.get("hwheel") or 0)
        if payload.get("x") is not None and payload.get("y") is not None:
            ok = bool(inj.wheel_abs(int(payload["x"]), int(payload["y"]), notches, h_notches, human=False))
        else:
            ok = bool(inj.wheel_here(notches, h_notches))
        return {"ok": ok, "kind": "wheel", "notches": notches, "error": None if ok else "wheel failed"}
    return {"ok": False, "error": f"unknown hid kind: {kind}"}


def pointer(step: Dict[str, Any]) -> Dict[str, Any]:
    if step.get("x") is None and step.get("y") is None and "move" not in step:
        return hid("pos", {})
    xy, err = _coords(step)
    if err or xy is None:
        return {"ok": False, "error": err or "pointer requires x,y"}
    x, y = xy
    return hid("move", {"x": x, "y": y, "human": bool(step.get("human", True))})


def mouse(step: Dict[str, Any]) -> Dict[str, Any]:
    action = str(step.get("action") or "").strip().lower()
    button = str(step.get("button") or step.get("click") or "left").strip().lower()
    if not action:
        if step.get("click"):
            action = "click"
        elif step.get("down"):
            action = "down"
            button = str(step.get("down") or button)
        elif step.get("up"):
            action = "up"
            button = str(step.get("up") or button)
        else:
            action = "click"
    if action not in {"click", "down", "up"}:
        return {"ok": False, "error": "mouse action must be click, down, or up"}
    payload: Dict[str, Any] = {"button": button, "human": bool(step.get("human", False))}
    if step.get("x") is not None or step.get("y") is not None:
        xy, err = _coords(step)
        if err or xy is None:
            return {"ok": False, "error": err or "mouse x,y invalid"}
        payload["x"], payload["y"] = xy
    return hid(action, payload)


def keypress(step: Dict[str, Any]) -> Dict[str, Any]:
    if step.get("text") and not (step.get("key") or step.get("name")):
        return hid("type", {"text": str(step.get("text") or "")})
    key = str(step.get("key") or step.get("name") or step.get("down") or step.get("up") or "").strip()
    action = str(step.get("action") or "tap").strip().lower()
    if step.get("down") and not step.get("key"):
        action = "down"
    if step.get("up") and not step.get("key"):
        action = "up"
    if not key:
        return {"ok": False, "error": "keypress requires key"}
    if action not in {"tap", "down", "up"}:
        return {"ok": False, "error": "keypress action must be tap, down, or up"}
    return hid("key", {"key": key, "action": action})


def _event_payload(event: Any) -> Tuple[str, Dict[str, Any]]:
    if not isinstance(event, dict):
        raise ValueError("each drive event must be an object")
    if "wait" in event:
        return "wait", {"ms": event.get("wait")}
    if "move" in event:
        pair = event.get("move")
        if isinstance(pair, (list, tuple)) and len(pair) >= 2:
            return "move", {"x": pair[0], "y": pair[1], "human": event.get("human", False)}
        return "move", event
    if "click" in event:
        return "click", {"button": event.get("click") or event.get("button") or "left", **_xy_only(event)}
    if "type" in event:
        return "type", {"text": event.get("type")}
    if "key" in event:
        return "key", {"key": event.get("key"), "action": event.get("action") or "tap"}
    if "down" in event:
        name = str(event.get("down") or "")
        if name in {"left", "right", "middle"}:
            return "down", {"button": name}
        return "key", {"key": name, "action": "down"}
    if "up" in event:
        name = str(event.get("up") or "")
        if name in {"left", "right", "middle"}:
            return "up", {"button": name}
        return "key", {"key": name, "action": "up"}
    if "wheel" in event:
        return "wheel", {"notches": event.get("wheel"), **_xy_only(event)}
    kind = str(event.get("op") or event.get("kind") or "").strip().lower()
    if kind:
        return kind, event
    raise ValueError("drive event needs move/click/type/key/wheel/wait")


def _xy_only(event: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    if event.get("x") is not None and event.get("y") is not None:
        out["x"] = event.get("x")
        out["y"] = event.get("y")
    return out


def apply_event(event: Any) -> Dict[str, Any]:
    kind, payload = _event_payload(event)
    if kind == "wait":
        try:
            ms = max(0.0, min(2000.0, float(payload.get("ms") or 0)))
        except (TypeError, ValueError):
            return {"ok": False, "error": "wait must be milliseconds"}
        if ms:
            time.sleep(ms / 1000.0)
        return {"ok": True, "kind": "wait", "ms": ms}
    return hid(kind, payload)


def drive(step: Dict[str, Any]) -> Dict[str, Any]:
    events = step.get("events") or step.get("burst") or step.get("input") or []
    if not isinstance(events, list):
        return {"ok": False, "error": "drive requires an events list"}
    if len(events) > MAX_DRIVE_EVENTS:
        return {"ok": False, "error": f"drive capped at {MAX_DRIVE_EVENTS} events"}
    kinds: List[str] = []
    for index, event in enumerate(events):
        try:
            result = apply_event(event)
        except ValueError as exc:
            return {"ok": False, "error": str(exc), "index": index, "count": len(kinds)}
        if not result.get("ok"):
            return {**result, "index": index, "count": len(kinds)}
        kinds.append(str(result.get("kind") or "ok"))
    return {"ok": True, "count": len(kinds), "kinds": kinds}
