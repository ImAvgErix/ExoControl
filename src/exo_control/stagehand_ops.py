"""Stagehand — NL act/extract on a page (Browserbase HTTP, Windows-safe).

Auth: ``BROWSERBASE_API_KEY`` or ``STAGEHAND_API_KEY`` (alias ``EXO_STAGEHAND_API_KEY``).
Optional ``MODEL_API_KEY``.
"""
from __future__ import annotations

import os
from typing import Any, Dict, Optional

from exo_control.http_json import env_key, error_from_http, request_json, timeout_of, user_agent

_REQUEST_JSON = None
DEFAULT_BASE = "https://api.stagehand.browserbase.com"


def api_key() -> Optional[str]:
    return env_key("BROWSERBASE_API_KEY", "STAGEHAND_API_KEY", "EXO_STAGEHAND_API_KEY")


def configured() -> bool:
    return bool(api_key())


def _auth_denied() -> Dict[str, Any]:
    return {
        "ok": False,
        "error": "stagehand requires BROWSERBASE_API_KEY or STAGEHAND_API_KEY",
        "code": "AUTHENTICATION",
        "hint": "export BROWSERBASE_API_KEY from https://www.browserbase.com",
    }


def _base() -> str:
    return (os.environ.get("STAGEHAND_API_URL") or os.environ.get("EXO_STAGEHAND_API_URL") or DEFAULT_BASE).rstrip("/")


def _headers(key: str) -> Dict[str, str]:
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": user_agent(),
    }
    model = env_key("MODEL_API_KEY", "EXO_MODEL_API_KEY")
    if model:
        headers["x-model-api-key"] = model
    return headers


def _call(method: str, url: str, headers: Dict[str, str], payload: Optional[Dict[str, Any]], timeout: float):
    if _REQUEST_JSON is not None:
        return _REQUEST_JSON(method, url, headers, payload, timeout)
    return request_json(method, url, headers, payload, timeout)


def _instruction(step: Dict[str, Any]) -> str:
    return str(step.get("instruction") or step.get("task") or step.get("text") or step.get("prompt") or "").strip()


def act(step: Dict[str, Any]) -> Dict[str, Any]:
    key = api_key()
    if not key:
        return _auth_denied()
    instruction = _instruction(step)
    if not instruction:
        return {"ok": False, "error": "stagehand requires instruction", "code": "MISSING_INSTRUCTION"}
    payload: Dict[str, Any] = {"instruction": instruction}
    url = str(step.get("url") or "").strip()
    if url:
        payload["url"] = url
    status, parsed, raw = _call("POST", f"{_base()}/v1/act", _headers(key), payload, timeout_of(step))
    if status not in {200, 201}:
        return error_from_http(status, parsed, raw, what="stagehand")
    return {
        "ok": True,
        "provider": "stagehand",
        "action": parsed.get("action") or parsed.get("result") or "ok",
        "data": parsed.get("data"),
        "url": url or None,
    }


def extract(step: Dict[str, Any]) -> Dict[str, Any]:
    key = api_key()
    if not key:
        return _auth_denied()
    instruction = _instruction(step) or str(step.get("query") or "").strip()
    if not instruction:
        return {"ok": False, "error": "stagehand_extract requires instruction", "code": "MISSING_INSTRUCTION"}
    payload: Dict[str, Any] = {"instruction": instruction}
    url = str(step.get("url") or "").strip()
    if url:
        payload["url"] = url
    schema = step.get("schema")
    if schema:
        payload["schema"] = schema
    status, parsed, raw = _call("POST", f"{_base()}/v1/extract", _headers(key), payload, timeout_of(step))
    if status not in {200, 201}:
        return error_from_http(status, parsed, raw, what="stagehand")
    data = parsed.get("data") if "data" in parsed else parsed.get("result") or parsed
    return {"ok": True, "provider": "stagehand", "data": data, "url": url or None}
