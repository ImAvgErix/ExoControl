"""Steel.dev cloud Chromium sessions (HTTP, Windows-reachable).

Auth: ``STEEL_API_KEY`` (alias ``EXO_STEEL_API_KEY``).
"""
from __future__ import annotations

import os
from typing import Any, Dict, Optional

from exo_control.http_json import env_key, error_from_http, request_json, timeout_of, user_agent

_REQUEST_JSON = None
DEFAULT_BASE = "https://api.steel.dev/v1"


def api_key() -> Optional[str]:
    return env_key("STEEL_API_KEY", "EXO_STEEL_API_KEY")


def configured() -> bool:
    return bool(api_key())


def _auth_denied(what: str = "steel") -> Dict[str, Any]:
    return {
        "ok": False,
        "error": f"{what} requires STEEL_API_KEY",
        "code": "AUTHENTICATION",
        "hint": "export STEEL_API_KEY from https://steel.dev",
    }


def _base() -> str:
    return (os.environ.get("STEEL_API_URL") or os.environ.get("EXO_STEEL_API_URL") or DEFAULT_BASE).rstrip("/")


def _headers(key: str) -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": user_agent(),
    }


def _call(method: str, url: str, headers: Dict[str, str], payload: Optional[Dict[str, Any]], timeout: float):
    if _REQUEST_JSON is not None:
        return _REQUEST_JSON(method, url, headers, payload, timeout)
    return request_json(method, url, headers, payload, timeout)


def start_session(step: Dict[str, Any]) -> Dict[str, Any]:
    key = api_key()
    if not key:
        return _auth_denied("steel_start")
    payload: Dict[str, Any] = {}
    if step.get("timeout") or step.get("session_timeout"):
        payload["timeout"] = int(step.get("session_timeout") or step.get("timeout") or 300000)
    status, parsed, raw = _call("POST", f"{_base()}/sessions", _headers(key), payload or {}, timeout_of(step))
    if status not in {200, 201}:
        return error_from_http(status, parsed, raw, what="steel_start")
    cdp = (
        parsed.get("websocketUrl")
        or parsed.get("cdpUrl")
        or parsed.get("cdp_url")
        or parsed.get("websocket_url")
        or ""
    )
    return {
        "ok": True,
        "provider": "steel",
        "id": parsed.get("id") or parsed.get("sessionId"),
        "cdp_url": cdp,
        "viewer": parsed.get("sessionViewerUrl") or parsed.get("debugUrl"),
    }


def stop_session(step: Dict[str, Any]) -> Dict[str, Any]:
    key = api_key()
    if not key:
        return _auth_denied("steel_stop")
    sid = str(step.get("id") or step.get("session_id") or step.get("session") or "").strip()
    if not sid:
        return {"ok": False, "error": "steel_stop requires id", "code": "MISSING_ID"}
    status, parsed, raw = _call("DELETE", f"{_base()}/sessions/{sid}", _headers(key), None, timeout_of(step))
    if status not in {200, 202, 204}:
        return error_from_http(status, parsed, raw, what="steel_stop")
    return {"ok": True, "provider": "steel", "id": sid, "stopped": True}
