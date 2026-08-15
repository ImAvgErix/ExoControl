"""Agent memory — local JSONL, optional Mem0 cloud.

Local always works (Windows-safe). ``MEM0_API_KEY`` (alias ``EXO_MEM0_API_KEY``)
sends add/search to Mem0 instead.
"""
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from exo_control.http_json import clip_int, env_key, error_from_http, request_json, timeout_of, user_agent
from exo_control.paths import state_dir

_REQUEST_JSON = None
MEM0_BASE = "https://api.mem0.ai/v1"


def api_key() -> Optional[str]:
    return env_key("MEM0_API_KEY", "EXO_MEM0_API_KEY")


def configured() -> bool:
    return True


def mem0_configured() -> bool:
    return bool(api_key())


def _store_path() -> Path:
    base = state_dir()
    base.mkdir(parents=True, exist_ok=True)
    return base / "agent_memory.jsonl"


def _headers(key: str) -> Dict[str, str]:
    return {
        "Authorization": f"Token {key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": user_agent(),
    }


def _call(method: str, url: str, headers: Dict[str, str], payload: Optional[Dict[str, Any]], timeout: float):
    if _REQUEST_JSON is not None:
        return _REQUEST_JSON(method, url, headers, payload, timeout)
    return request_json(method, url, headers, payload, timeout)


def _user(step: Dict[str, Any]) -> str:
    return str(step.get("user_id") or step.get("user") or "default").strip() or "default"


def _text(step: Dict[str, Any]) -> str:
    return str(step.get("text") or step.get("memory") or step.get("content") or step.get("fact") or "").strip()


def add(step: Dict[str, Any]) -> Dict[str, Any]:
    text = _text(step)
    if not text:
        return {"ok": False, "error": "memory_add requires text", "code": "MISSING_TEXT"}
    user = _user(step)
    key = api_key()
    if key:
        payload = {"messages": [{"role": "user", "content": text}], "user_id": user}
        status, parsed, raw = _call(
            "POST", f"{MEM0_BASE}/memories/", _headers(key), payload, timeout_of(step)
        )
        if status not in {200, 201}:
            return error_from_http(status, parsed, raw, what="memory")
        return {
            "ok": True,
            "provider": "mem0",
            "id": parsed.get("id") or (parsed.get("results") or [{}])[0].get("id") if isinstance(parsed.get("results"), list) else parsed.get("id"),
            "user_id": user,
        }
    rec = {"id": uuid.uuid4().hex[:12], "text": text, "user_id": user, "ts": time.time()}
    with open(_store_path(), "a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return {"ok": True, "provider": "local", "id": rec["id"], "user_id": user}


def _load_local(user: str) -> List[Dict[str, Any]]:
    path = _store_path()
    if not path.exists():
        return []
    out: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(rec, dict):
            continue
        if user and rec.get("user_id") not in {user, None, ""}:
            if rec.get("user_id") != user:
                continue
        out.append(rec)
    return out


def search(step: Dict[str, Any]) -> Dict[str, Any]:
    query = str(step.get("query") or step.get("q") or step.get("text") or "").strip()
    if not query:
        return {"ok": False, "error": "memory_search requires query", "code": "MISSING_QUERY"}
    user = _user(step)
    limit = clip_int(step.get("max") or step.get("limit") or 8, 8, 1, 40)
    key = api_key()
    if key:
        payload = {"query": query, "user_id": user}
        status, parsed, raw = _call(
            "POST", f"{MEM0_BASE}/memories/search/", _headers(key), payload, timeout_of(step)
        )
        if status not in {200, 201}:
            return error_from_http(status, parsed, raw, what="memory")
        rows = parsed.get("results") or parsed.get("memories") or parsed.get("value") or []
        if not isinstance(rows, list):
            rows = []
        memories = []
        for item in rows[:limit]:
            if isinstance(item, dict):
                memories.append({
                    "id": item.get("id"),
                    "text": item.get("memory") or item.get("text") or item.get("content"),
                })
            elif isinstance(item, str):
                memories.append({"text": item})
        return {"ok": True, "provider": "mem0", "query": query, "memories": memories, "count": len(memories)}
    needle = query.lower()
    hits = []
    for rec in reversed(_load_local(user)):
        blob = str(rec.get("text") or "").lower()
        if needle in blob:
            hits.append({"id": rec.get("id"), "text": rec.get("text"), "ts": rec.get("ts")})
        if len(hits) >= limit:
            break
    return {"ok": True, "provider": "local", "query": query, "memories": hits, "count": len(hits)}
