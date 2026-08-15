"""Jina Reader — URL to markdown (HTTP, Windows-safe).

``GET https://r.jina.ai/{url}``. Optional ``JINA_API_KEY`` / ``EXO_JINA_API_KEY``.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from exo_control.http_json import env_key, error_from_http, request_text, timeout_of, truncate, user_agent

_REQUEST_TEXT = None
READER = "https://r.jina.ai"


def api_key() -> Optional[str]:
    return env_key("JINA_API_KEY", "EXO_JINA_API_KEY")


def configured() -> bool:
    return True


def _headers() -> Dict[str, str]:
    headers = {
        "Accept": "text/plain, text/markdown, */*",
        "User-Agent": user_agent(),
        "X-Return-Format": "markdown",
    }
    key = api_key()
    if key:
        headers["Authorization"] = f"Bearer {key}"
    return headers


def _call(method: str, url: str, headers: Dict[str, str], timeout: float):
    if _REQUEST_TEXT is not None:
        return _REQUEST_TEXT(method, url, headers, timeout)
    return request_text(method, url, headers, timeout)


def read_url(step: Dict[str, Any]) -> Dict[str, Any]:
    target = str(step.get("url") or step.get("href") or step.get("page") or "").strip()
    if not target:
        return {"ok": False, "error": "read_url requires url", "code": "MISSING_URL"}
    if not target.lower().startswith(("http://", "https://")):
        target = "https://" + target
    url = f"{READER}/{target}"
    status, text, raw = _call("GET", url, _headers(), timeout_of(step, default=45.0, hi=90.0))
    if status not in {200, 201}:
        parsed = {"error": text or raw}
        return error_from_http(status, parsed, raw or text, what="read_url")
    verbose = step.get("verbose") is True
    limit = 16000 if verbose else 6000
    return {
        "ok": True,
        "provider": "jina",
        "url": target,
        "markdown": truncate(text, limit),
        "chars": len(text),
    }
