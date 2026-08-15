"""Everything (voidtools) — instant Windows file find, with walk fallback.

HTTP: ``EVERYTHING_URL`` (default ``http://127.0.0.1``). Results stay allowrooted.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

from exo_control.files_ops import _resolve_under_roots, default_roots
from exo_control.http_json import clip_int, env_key, request_json, timeout_of, user_agent

_REQUEST_JSON = None


def service_url() -> str:
    return (env_key("EVERYTHING_URL", "EXO_EVERYTHING_URL") or "http://127.0.0.1").rstrip("/")


def configured() -> bool:
    return True


def _call(method: str, url: str, headers: Dict[str, str], payload: Optional[Dict[str, Any]], timeout: float):
    if _REQUEST_JSON is not None:
        return _REQUEST_JSON(method, url, headers, payload, timeout)
    return request_json(method, url, headers, payload, timeout)


def _full_path(item: Dict[str, Any]) -> str:
    p = str(item.get("path") or item.get("full_path") or "")
    n = str(item.get("name") or item.get("file") or "")
    if p and n:
        try:
            joined = str(Path(p) / n)
        except Exception:
            joined = p.rstrip("\\/") + os.sep + n
        if n in p.replace("/", "\\"):
            return p
        return joined
    return p or n


def _under_roots(path: str) -> bool:
    ok, resolved, outside = _resolve_under_roots(path)
    return bool(ok) and not outside


def _walk(query: str, limit: int) -> List[Dict[str, Any]]:
    q = query.lower()
    globby = any(ch in query for ch in "*?[]")
    hits: List[Dict[str, Any]] = []
    for root in default_roots():
        try:
            root_r = root.resolve()
        except OSError:
            continue
        if not root_r.is_dir():
            continue
        try:
            iterator = root_r.rglob(query) if globby else root_r.rglob("*")
        except OSError:
            continue
        for entry in iterator:
            try:
                if not entry.is_file():
                    continue
                name = entry.name
                if not globby and q not in name.lower() and q not in str(entry).lower():
                    continue
                hits.append({"name": name, "path": str(entry), "is_dir": False})
                if len(hits) >= limit:
                    return hits
            except OSError:
                continue
    return hits


def find(step: Dict[str, Any]) -> Dict[str, Any]:
    query = str(step.get("query") or step.get("q") or step.get("name") or step.get("pattern") or "").strip()
    if not query:
        return {"ok": False, "error": "files_find requires query", "code": "MISSING_QUERY"}
    limit = clip_int(step.get("max") or step.get("limit") or 20, 20, 1, 80)
    params = urlencode({"search": query, "json": 1, "path_column": 1, "n": limit})
    url = f"{service_url()}/?{params}"
    status, parsed, _raw = _call(
        "GET",
        url,
        {"Accept": "application/json", "User-Agent": user_agent()},
        None,
        timeout_of(step, default=8.0, hi=20.0),
    )
    if status in {200, 201} and (parsed.get("results") is not None or parsed.get("value") is not None):
        raw_hits = parsed.get("results") or parsed.get("value") or []
        if not isinstance(raw_hits, list):
            raw_hits = []
        kept: List[Dict[str, Any]] = []
        for item in raw_hits:
            if not isinstance(item, dict):
                continue
            full = _full_path(item)
            if not full or not _under_roots(full):
                continue
            kept.append({"name": item.get("name") or Path(full).name, "path": full})
            if len(kept) >= limit:
                break
        return {
            "ok": True,
            "provider": "everything",
            "query": query,
            "results": kept,
            "count": len(kept),
            "fallback": None,
        }
    walked = _walk(query, limit)
    return {
        "ok": True,
        "provider": "everything",
        "query": query,
        "results": walked,
        "count": len(walked),
        "fallback": "walk",
    }
