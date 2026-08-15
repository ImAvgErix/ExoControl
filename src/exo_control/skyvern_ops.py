"""Skyvern — vision-first browser workflows (HTTP, Windows-safe).

Auth: ``SKYVERN_API_KEY`` (alias ``EXO_SKYVERN_API_KEY``).
"""
from __future__ import annotations

import os
from typing import Any, Dict, Optional

from exo_control.http_json import env_key, error_from_http, request_json, timeout_of, user_agent

_REQUEST_JSON = None
DEFAULT_BASE = "https://api.skyvern.com"


def api_key() -> Optional[str]:
    return env_key("SKYVERN_API_KEY", "EXO_SKYVERN_API_KEY")


def configured() -> bool:
    return bool(api_key())


def _auth_denied() -> Dict[str, Any]:
    return {
        "ok": False,
        "error": "skyvern requires SKYVERN_API_KEY",
        "code": "AUTHENTICATION",
        "hint": "export SKYVERN_API_KEY from https://app.skyvern.com/settings",
    }


def _base() -> str:
    return (os.environ.get("SKYVERN_API_URL") or os.environ.get("EXO_SKYVERN_API_URL") or DEFAULT_BASE).rstrip("/")


def _headers(key: str) -> Dict[str, str]:
    return {
        "x-api-key": key,
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": user_agent(),
    }


def _call(method: str, url: str, headers: Dict[str, str], payload: Optional[Dict[str, Any]], timeout: float):
    if _REQUEST_JSON is not None:
        return _REQUEST_JSON(method, url, headers, payload, timeout)
    return request_json(method, url, headers, payload, timeout)


def run_task(step: Dict[str, Any]) -> Dict[str, Any]:
    key = api_key()
    if not key:
        return _auth_denied()
    run_id = str(step.get("run_id") or step.get("id") or "").strip()
    headers = _headers(key)
    timeout = timeout_of(step)
    if run_id:
        status, parsed, raw = _call("GET", f"{_base()}/v1/run/tasks/{run_id}", headers, None, timeout)
        if status != 200:
            return error_from_http(status, parsed, raw, what="skyvern")
        return {
            "ok": True,
            "provider": "skyvern",
            "run_id": parsed.get("run_id") or parsed.get("id") or run_id,
            "status": parsed.get("status"),
            "output": parsed.get("output") or parsed.get("extracted_information"),
        }
    prompt = str(step.get("task") or step.get("prompt") or step.get("text") or step.get("instruction") or "").strip()
    if not prompt:
        return {"ok": False, "error": "skyvern requires task or run_id", "code": "MISSING_TASK"}
    payload: Dict[str, Any] = {"prompt": prompt}
    url = str(step.get("url") or "").strip()
    if url:
        payload["url"] = url
    status, parsed, raw = _call("POST", f"{_base()}/v1/run/tasks", headers, payload, timeout)
    if status not in {200, 201}:
        return error_from_http(status, parsed, raw, what="skyvern")
    return {
        "ok": True,
        "provider": "skyvern",
        "run_id": parsed.get("run_id") or parsed.get("id"),
        "status": parsed.get("status") or "created",
        "output": parsed.get("output"),
    }
