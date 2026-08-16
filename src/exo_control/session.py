"""Persistent agent session — preferences, checkpoints, recovery.

State: ``~/.exo/state/sessions/<agent_id>.json`` (or EXO_STATE_DIR).
Keeps the machine feeling like *this* agent's PC across process restarts.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

_AGENT_RE = re.compile(r"[^A-Za-z0-9._-]+")


def _sessions_dir() -> Path:
    from exo_control.paths import state_dir

    d = state_dir() / "sessions"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _safe_agent(agent_id: str) -> str:
    raw = _AGENT_RE.sub("_", (agent_id or "").strip())[:80]
    return raw or "default"


def _path(agent_id: str) -> Path:
    return _sessions_dir() / f"{_safe_agent(agent_id)}.json"


def _empty(agent_id: str) -> Dict[str, Any]:
    now = time.time()
    return {
        "agent_id": _safe_agent(agent_id),
        "created_at": now,
        "updated_at": now,
        "prefs": {},
        "notes": [],
        "focus_stack": [],
        "checkpoint": None,
        "plan": None,
        "stats": {"hands": 0, "recovers": 0},
        "hits": [],
    }


def load(agent_id: str) -> Dict[str, Any]:
    path = _path(agent_id)
    if not path.is_file():
        return _empty(agent_id)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return _empty(agent_id)
        base = _empty(agent_id)
        base.update(data)
        base["agent_id"] = _safe_agent(agent_id)
        return base
    except (OSError, json.JSONDecodeError):
        return _empty(agent_id)


def save(data: Dict[str, Any]) -> None:
    agent_id = str(data.get("agent_id") or "default")
    data["updated_at"] = time.time()
    path = _path(agent_id)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    tmp.replace(path)


def start(agent_id: str, *, task: str = "") -> Dict[str, Any]:
    data = load(agent_id)
    if task:
        data["last_task"] = str(task)
    data["active"] = True
    save(data)
    return {"ok": True, "session": _public(data), "resumed": bool(data.get("checkpoint") or data.get("prefs"))}


def end(agent_id: str) -> Dict[str, Any]:
    data = load(agent_id)
    data["active"] = False
    save(data)
    return {"ok": True, "session": _public(data)}


def status(agent_id: str) -> Dict[str, Any]:
    data = load(agent_id)
    return {"ok": True, "session": _public(data)}


def remember(agent_id: str, key: str, value: Any) -> Dict[str, Any]:
    key = str(key or "").strip()
    if not key:
        return {"ok": False, "error": "remember requires key"}
    data = load(agent_id)
    prefs = dict(data.get("prefs") or {})
    prefs[key] = value
    if len(prefs) > 200:
        # drop oldest insertion order
        prefs = dict(list(prefs.items())[-200:])
    data["prefs"] = prefs
    save(data)
    return {"ok": True, "key": key, "stored": True}


def recall(agent_id: str, key: Optional[str] = None) -> Dict[str, Any]:
    data = load(agent_id)
    prefs = data.get("prefs") or {}
    if key:
        if key not in prefs:
            return {"ok": False, "error": "unknown key", "key": key}
        return {"ok": True, "key": key, "value": prefs[key]}
    return {"ok": True, "prefs": prefs, "count": len(prefs)}


def note(agent_id: str, text: str) -> Dict[str, Any]:
    text = str(text or "").strip()
    if not text:
        return {"ok": False, "error": "note requires text"}
    data = load(agent_id)
    notes: List[Dict[str, Any]] = list(data.get("notes") or [])
    notes.append({"ts": time.time(), "text": text[:2000]})
    data["notes"] = notes[-50:]
    save(data)
    return {"ok": True, "count": len(data["notes"])}


def push_focus(agent_id: str, focus: Dict[str, Any]) -> None:
    if not agent_id or not isinstance(focus, dict):
        return
    data = load(agent_id)
    stack: List[Dict[str, Any]] = list(data.get("focus_stack") or [])
    entry = {
        "ts": time.time(),
        "title": focus.get("title"),
        "pid": focus.get("pid"),
        "window_id": focus.get("window_id") or focus.get("hwnd"),
        "monitor": focus.get("monitor"),
    }
    stack.append(entry)
    data["focus_stack"] = stack[-12:]
    data["last_focus"] = entry
    save(data)


def last_focus(agent_id: str) -> Optional[Dict[str, Any]]:
    data = load(agent_id)
    stack = data.get("focus_stack") or []
    if stack:
        return dict(stack[-1])
    lf = data.get("last_focus")
    return dict(lf) if isinstance(lf, dict) else None


def checkpoint(
    agent_id: str,
    *,
    focus: Optional[Dict[str, Any]] = None,
    url: Optional[str] = None,
    space_id: Optional[str] = None,
    path: Optional[str] = None,
    note_text: Optional[str] = None,
) -> Dict[str, Any]:
    data = load(agent_id)
    cp = {
        "ts": time.time(),
        "focus": focus or last_focus(agent_id),
        "url": url,
        "space_id": space_id,
        "path": path,
        "note": (note_text or "")[:500] or None,
    }
    data["checkpoint"] = cp
    save(data)
    return {"ok": True, "checkpoint": cp}


def get_checkpoint(agent_id: str) -> Optional[Dict[str, Any]]:
    data = load(agent_id)
    cp = data.get("checkpoint")
    return dict(cp) if isinstance(cp, dict) else None


def set_plan(agent_id: str, goal: str, steps: Optional[List[Any]] = None) -> Dict[str, Any]:
    goal = str(goal or "").strip()
    if not goal:
        return {"ok": False, "error": "plan requires goal"}
    data = load(agent_id)
    plan = {
        "goal": goal[:2000],
        "steps": list(steps or [])[:40],
        "ts": time.time(),
        "index": 0,
    }
    data["plan"] = plan
    save(data)
    return {"ok": True, "plan": plan}


def bump_stat(agent_id: str, name: str, n: int = 1) -> None:
    data = load(agent_id)
    stats = dict(data.get("stats") or {})
    stats[name] = int(stats.get(name) or 0) + n
    data["stats"] = stats
    save(data)


def _public(data: Dict[str, Any]) -> Dict[str, Any]:
    prefs = data.get("prefs") or {}
    return {
        "agent_id": data.get("agent_id"),
        "active": bool(data.get("active")),
        "last_task": data.get("last_task"),
        "prefs_count": len(prefs),
        "notes": (data.get("notes") or [])[-5:],
        "focus_stack": (data.get("focus_stack") or [])[-4:],
        "checkpoint": data.get("checkpoint"),
        "plan": data.get("plan"),
        "stats": data.get("stats") or {},
        "updated_at": data.get("updated_at"),
        "hits_count": len(_HIT_CACHE),
    }


# In-memory fused-observe hit cache. Replaced on each observe, cleared on
# session_close, readable by the next exec() in this process. Not persisted.


def _hits_path():
    from exo_control.paths import state_dir
    return state_dir() / "session_hits.json"


def _persist_hits(hits):
    path = _hits_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(hits[:40], indent=2, default=str), encoding="utf-8")


def _load_persisted_hits():
    path = _hits_path()
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return [h for h in data if isinstance(h, dict)] if isinstance(data, list) else []
    except (OSError, json.JSONDecodeError):
        return []

_HIT_CACHE: List[Dict[str, Any]] = []


def _as_hit(raw: Dict[str, Any], *, ref: str = "", source: str = "") -> Dict[str, Any]:
    bbox = raw.get("bbox")
    if not isinstance(bbox, list):
        bbox = raw.get("bounds")
    return {
        "ref": str(raw.get("ref") or ref or ""),
        "label": raw.get("label") or raw.get("name") or raw.get("text") or "",
        "kind": raw.get("kind") or raw.get("role") or "",
        "bbox": bbox if isinstance(bbox, list) else None,
        "source": raw.get("source") or source or "",
        "visible": bool(raw.get("visible", True)),
        "element_index": raw.get("element_index"),
        "pid": raw.get("pid"),
        "window_id": raw.get("window_id") or raw.get("hwnd"),
    }


def replace_hits(hits: List[Any]) -> List[Dict[str, Any]]:
    """Replace the live observe hit cache."""
    global _HIT_CACHE
    cleaned: List[Dict[str, Any]] = []
    for i, raw in enumerate(hits or []):
        if not isinstance(raw, dict):
            continue
        item = _as_hit(raw, ref=f"e{i}", source=str(raw.get("source") or ""))
        if not item["ref"]:
            item["ref"] = f"e{i}"
        cleaned.append(item)
    _HIT_CACHE = cleaned
    try:
        _persist_hits(_HIT_CACHE)
    except Exception:
        pass
    return list(_HIT_CACHE)


def get_hits() -> List[Dict[str, Any]]:
    if not _HIT_CACHE:
        loaded = _load_persisted_hits()
        if loaded:
            _HIT_CACHE.extend(loaded)
    return list(_HIT_CACHE)


def clear_hits() -> None:
    global _HIT_CACHE
    _HIT_CACHE = []
    try:
        _hits_path().unlink(missing_ok=True)
    except Exception:
        pass


def lookup_hit(
    ref: Optional[str] = None,
    label: Optional[str] = None,
    kind: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    needle_ref = str(ref).strip() if ref is not None else ""
    needle_label = (label or "").strip().lower()
    needle_kind = (kind or "").strip().lower()
    for hit in _HIT_CACHE:
        if not hit.get("visible", True):
            continue
        href = str(hit.get("ref") or "")
        if needle_ref:
            if href == needle_ref or (needle_ref.isdigit() and href == f"e{needle_ref}"):
                return dict(hit)
            continue
        if needle_kind and str(hit.get("kind") or "").lower() != needle_kind:
            continue
        if needle_label:
            hl = str(hit.get("label") or "").lower()
            if needle_label == hl or needle_label in hl or (hl and hl in needle_label):
                return dict(hit)
            continue
        if needle_kind:
            return dict(hit)
    return None
