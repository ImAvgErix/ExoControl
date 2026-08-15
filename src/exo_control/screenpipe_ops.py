"""Screenpipe — local searchable screen/audio history.

Default ``http://127.0.0.1:3030``. Override with ``SCREENPIPE_URL``.
"""
from __future__ import annotations

from typing import Any, Dict, Optional
from urllib.parse import urlencode

from exo_control.http_json import clip_int, env_key, error_from_http, request_json, timeout_of, user_agent

_REQUEST_JSON = None
DEFAULT_BASE = "http://127.0.0.1:3030"


def service_url() -> str:
    return (env_key("SCREENPIPE_URL", "EXO_SCREENPIPE_URL") or DEFAULT_BASE).rstrip("/")


def configured() -> bool:
    return True


def _call(method: str, url: str, headers: Dict[str, str], payload: Optional[Dict[str, Any]], timeout: float):
    if _REQUEST_JSON is not None:
        return _REQUEST_JSON(method, url, headers, payload, timeout)
    return request_json(method, url, headers, payload, timeout)


def search(step: Dict[str, Any]) -> Dict[str, Any]:
    query = str(step.get("query") or step.get("q") or step.get("text") or "").strip()
    limit = clip_int(step.get("max") or step.get("limit") or 10, 10, 1, 40)
    params = {"limit": str(limit), "content_type": str(step.get("content_type") or "all")}
    if query:
        params["q"] = query
    app = str(step.get("app") or step.get("app_name") or "").strip()
    if app:
        params["app_name"] = app
    url = f"{service_url()}/search?{urlencode(params)}"
    headers = {"Accept": "application/json", "User-Agent": user_agent()}
    token = env_key("SCREENPIPE_API_KEY", "EXO_SCREENPIPE_API_KEY")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    status, parsed, raw = _call("GET", url, headers, None, timeout_of(step, default=8.0, hi=20.0))
    if status == 0:
        return {
            "ok": False,
            "error": "screenpipe is not running on localhost:3030",
            "code": "CONNECT",
            "hint": "start Screenpipe and/or set SCREENPIPE_URL",
        }
    if status not in {200, 201}:
        return error_from_http(status, parsed, raw, what="recall")
    rows = parsed.get("data") or parsed.get("results") or parsed.get("value") or []
    if not isinstance(rows, list):
        rows = []
    compact = []
    for item in rows[:limit]:
        if isinstance(item, dict):
            compact.append({
                "content": item.get("content") or item.get("text") or item.get("ocr_text"),
                "app": item.get("app_name") or item.get("app"),
                "ts": item.get("timestamp") or item.get("ts"),
            })
        elif isinstance(item, str):
            compact.append({"content": item})
    return {
        "ok": True,
        "provider": "screenpipe",
        "query": query or None,
        "results": compact,
        "count": len(compact),
    }
