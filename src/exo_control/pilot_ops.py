"""Exo Pilot — original control-plane features, not vendor HTTP wrappers.

Playwright-MCP and Computer Use give you clicks. Pilot gives the agent a job:

- ``goal`` / ``checkpoint`` / ``proof`` — declare intent and emit evidence
- ``changed`` — structured diff of the last two eye glances
- ``undo`` — reverse the last reversible mutation we journaled
- ``skill_save`` / ``skill_run`` — muscle memory from a successful script
- ``heal`` — one bounded retry of the last failed hand
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from exo_control import files_ops
from exo_control.paths import state_dir

META_OPS = frozenset({
    "goal", "intent", "checkpoint", "proof",
    "changed", "what_changed",
    "undo",
    "skill_save", "skill_run", "skill_list", "replay",
    "heal", "ready", "readiness",
    "help", "ops", "capabilities", "catalog", "status", "stats",
    "lease_acquire", "lease_renew", "lease_release", "lease_status", "lease_force_release",
    "session_open", "seat", "take_seat",
    "session_close", "leave_seat", "session_end",
    "session_status", "seat_status",
    "last_error", "error", "last_fail",
    "action_log", "log", "recent_actions",
})

_NAME_OK = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
_UNDO_LIMIT = 20
_GLANCE_LIMIT = 2


def _skills_dir() -> Path:
    root = state_dir() / "skills"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _safe_name(raw: Any) -> Optional[str]:
    name = str(raw or "").strip()
    if not _NAME_OK.match(name):
        return None
    return name


def glance_from(value: Any) -> Dict[str, Any]:
    if not isinstance(value, dict):
        return {"title": "", "labels": []}
    labels: List[str] = []
    for key in ("a11y_labels", "labels"):
        raw = value.get(key) or []
        if not isinstance(raw, list):
            continue
        for item in raw:
            if isinstance(item, str) and item.strip():
                labels.append(item.strip())
            elif isinstance(item, dict):
                text = item.get("label") or item.get("name") or item.get("text")
                if text:
                    labels.append(str(text).strip())
    a11y = value.get("a11y") or []
    if isinstance(a11y, list):
        for item in a11y:
            if isinstance(item, dict):
                text = item.get("label") or item.get("name")
                if text:
                    labels.append(str(text).strip())
    # de-dupe, keep order
    seen = set()
    uniq: List[str] = []
    for label in labels:
        if label and label not in seen:
            seen.add(label)
            uniq.append(label)
        if len(uniq) >= 40:
            break
    return {"title": str(value.get("title") or ""), "labels": uniq}


class Pilot:
    def __init__(self) -> None:
        self.goal: Optional[str] = None
        self.checkpoints: List[Dict[str, Any]] = []
        self.glances: List[Dict[str, Any]] = []
        self.undo_stack: List[Dict[str, Any]] = []
        self.script: List[Dict[str, Any]] = []
        self.last_failed_step: Optional[Dict[str, Any]] = None
        self.heal_used: bool = False
        self.done: bool = False

    def reset_script(self) -> None:
        self.script = []

    def set_goal(self, step: Dict[str, Any]) -> Dict[str, Any]:
        text = str(step.get("text") or step.get("goal") or step.get("intent") or "").strip()
        if not text:
            return {"ok": False, "error": "goal requires text", "code": "MISSING_GOAL"}
        self.goal = text
        self.checkpoints = []
        self.done = False
        return {"ok": True, "goal": text}

    def checkpoint(self, step: Dict[str, Any]) -> Dict[str, Any]:
        note = str(step.get("note") or step.get("text") or step.get("name") or "").strip()
        if not note:
            return {"ok": False, "error": "checkpoint requires note", "code": "MISSING_NOTE"}
        row = {"note": note, "ts": time.time()}
        if step.get("done") is True:
            row["done"] = True
            self.done = True
        self.checkpoints.append(row)
        return {"ok": True, "note": note, "count": len(self.checkpoints), "done": self.done}

    def proof(self, last_error: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        last = self.glances[-1] if self.glances else None
        return {
            "ok": True,
            "goal": self.goal,
            "checkpoints": list(self.checkpoints),
            "done": self.done,
            "undo": len(self.undo_stack),
            "skills_ready": bool(self.script),
            "glance": {"title": last["title"], "labels": last["labels"][:12]} if last else None,
            "last_error": (last_error or {}).get("error") if last_error else None,
        }

    def summary(self) -> Dict[str, Any]:
        return {
            "goal": self.goal,
            "checkpoints": len(self.checkpoints),
            "done": self.done,
            "undo": len(self.undo_stack),
        }

    def note_glance(self, value: Any) -> None:
        self.glances.append(glance_from(value))
        if len(self.glances) > _GLANCE_LIMIT:
            del self.glances[: len(self.glances) - _GLANCE_LIMIT]

    def changed(self) -> Dict[str, Any]:
        if len(self.glances) < 2:
            return {
                "ok": False,
                "error": "changed needs two glances (observe/read first)",
                "code": "NEED_GLANCES",
            }
        before, after = self.glances[-2], self.glances[-1]
        old = set(before.get("labels") or [])
        new = set(after.get("labels") or [])
        added = sorted(new - old)
        removed = sorted(old - new)
        return {
            "ok": True,
            "added": added,
            "removed": removed,
            "title_before": before.get("title") or "",
            "title_after": after.get("title") or "",
            "same": not added and not removed and before.get("title") == after.get("title"),
        }

    def remember_step(self, step: Dict[str, Any], op: str) -> None:
        if op in META_OPS:
            return
        clean = {k: v for k, v in step.items() if k != "_op" and not str(k).startswith("_")}
        clean["op"] = op
        self.script.append(clean)

    def note_failure(self, step: Dict[str, Any], op: str) -> None:
        clean = {k: v for k, v in step.items() if k != "_op" and not str(k).startswith("_")}
        clean["op"] = op
        self.last_failed_step = clean
        self.heal_used = False

    def prepare_undo(self, op: str, step: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if op == "files_write":
            path = str(step.get("path") or "")
            if not path:
                return None
            got = files_ops.files_read(path)
            if got.get("ok"):
                return {"kind": "files_write", "path": got.get("path") or path, "existed": True, "text": got.get("text") or ""}
            return {"kind": "files_write", "path": path, "existed": False, "text": ""}
        if op == "files_delete":
            path = str(step.get("path") or "")
            if not path:
                return None
            got = files_ops.files_read(path)
            if not got.get("ok"):
                return None
            return {"kind": "files_delete", "path": got.get("path") or path, "text": got.get("text") or ""}
        if op == "clipboard_set":
            return {"kind": "clipboard_set", "text": step.get("_prev_clipboard")}
        return None

    def push_undo(self, snap: Dict[str, Any]) -> None:
        self.undo_stack.append(snap)
        if len(self.undo_stack) > _UNDO_LIMIT:
            del self.undo_stack[: len(self.undo_stack) - _UNDO_LIMIT]

    def undo(self) -> Dict[str, Any]:
        if not self.undo_stack:
            return {"ok": False, "error": "nothing to undo", "code": "EMPTY_UNDO"}
        snap = self.undo_stack.pop()
        kind = snap.get("kind")
        if kind == "files_write":
            path = str(snap.get("path") or "")
            if snap.get("existed"):
                out = files_ops.files_write(path, str(snap.get("text") or ""), confirm=True)
                return {**out, "undid": "files_write", "restored": True}
            out = files_ops.files_delete(path, confirm=True)
            return {**out, "undid": "files_write", "removed": True}
        if kind == "files_delete":
            out = files_ops.files_write(str(snap.get("path") or ""), str(snap.get("text") or ""), confirm=True)
            return {**out, "undid": "files_delete", "restored": True}
        if kind == "clipboard_set":
            prev = snap.get("text")
            if prev is None:
                return {"ok": False, "error": "clipboard undo has no prior text", "code": "EMPTY_UNDO"}
            return {"ok": True, "undid": "clipboard_set", "text": prev, "restore": True}
        return {"ok": False, "error": f"cannot undo {kind}", "code": "NOT_REVERSIBLE"}

    def skill_save(self, step: Dict[str, Any]) -> Dict[str, Any]:
        name = _safe_name(step.get("name") or step.get("skill") or step.get("id"))
        if not name:
            return {"ok": False, "error": "skill_save requires name (letters/digits/._-)", "code": "BAD_NAME"}
        steps = step.get("steps") or step.get("script")
        if isinstance(steps, list) and steps:
            payload = [s for s in steps if isinstance(s, dict) and s.get("op")]
        else:
            payload = [s for s in self.script if s.get("op") not in META_OPS]
        if not payload:
            return {"ok": False, "error": "nothing to save (run hands first, or pass steps=)", "code": "EMPTY_SKILL"}
        path = _skills_dir() / f"{name}.json"
        path.write_text(json.dumps({"name": name, "steps": payload, "ts": time.time()}, indent=2), encoding="utf-8")
        return {"ok": True, "name": name, "count": len(payload), "path": str(path)}

    def skill_list(self) -> Dict[str, Any]:
        names = sorted(p.stem for p in _skills_dir().glob("*.json"))
        return {"ok": True, "skills": names, "count": len(names)}

    def skill_load(self, step: Dict[str, Any]) -> Dict[str, Any]:
        name = _safe_name(step.get("name") or step.get("skill") or step.get("id"))
        if not name:
            return {"ok": False, "error": "skill_run requires name", "code": "BAD_NAME"}
        path = _skills_dir() / f"{name}.json"
        if not path.is_file():
            return {"ok": False, "error": f"skill not found: {name}", "code": "NOT_FOUND"}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            return {"ok": False, "error": f"skill corrupt: {exc}", "code": "BAD_SKILL"}
        steps = [s for s in (data.get("steps") or []) if isinstance(s, dict)]
        steps = [s for s in steps if str(s.get("op") or "") not in {"skill_run", "replay", "skill_save"}]
        if not steps:
            return {"ok": False, "error": "skill has no steps", "code": "EMPTY_SKILL"}
        return {"ok": True, "name": name, "steps": steps, "count": len(steps)}
