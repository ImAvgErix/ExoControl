"""AgentQL — English/schema query over a live URL (HTTP, Windows-safe).

Auth: ``AGENTQL_API_KEY`` (alias ``EXO_AGENTQL_API_KEY``).
"""
from __future__ import annotations

import os
from typing import Any, Dict, Optional

from exo_control.http_json import env_key, error_from_http, request_json, timeout_of, user_agent

_REQUEST_JSON = None
DEFAULT_BASE = "https://api.agentql.com"


def api_key() -> Optional[str]:
    return env_key("AGENTQL_API_KEY", "EXO_AGENTQL_API_KEY")


def configured() -> bool:
    return bool(api_key())


def _auth_denied() -> Dict[str, Any]:
    return {
        "ok": False,
        "error": "agentql requires AGENTQL_API_KEY",
        "code": "AUTHENTICATION",
        "hint": "export AGENTQL_API_KEY from https://www.agentql.com",
    }


def _base() -> str:
    return (os.environ.get("AGENTQL_API_URL") or os.environ.get("EXO_AGENTQL_API_URL") or DEFAULT_BASE).rstrip("/")


def _headers(key: str) -> Dict[str, str]:
    return {
        "X-API-Key": key,
        "x-api-key": key,
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": user_agent(),
    }


def _call(method: str, url: str, headers: Dict[str, str], payload: Optional[Dict[str, Any]], timeout: float):
    if _REQUEST_JSON is not None:
        return _REQUEST_JSON(method, url, headers, payload, timeout)
    return request_json(method, url, headers, payload, timeout)


def query(step: Dict[str, Any]) -> Dict[str, Any]:
    key = api_key()
    if not key:
        return _auth_denied()
    url = str(step.get("url") or step.get("page") or "").strip()
    q = str(step.get("query") or step.get("ql") or step.get("schema") or "").strip()
    if not url:
        return {"ok": False, "error": "agentql requires url", "code": "MISSING_URL"}
    if not q:
        return {"ok": False, "error": "agentql requires query", "code": "MISSING_QUERY"}
    payload: Dict[str, Any] = {"url": url, "query": q}
    status, parsed, raw = _call(
        "POST", f"{_base()}/v1/query-data", _headers(key), payload, timeout_of(step)
    )
    if status not in {200, 201}:
        return error_from_http(status, parsed, raw, what="agentql")
    data = parsed.get("data") if "data" in parsed else parsed
    return {"ok": True, "provider": "agentql", "url": url, "data": data}
