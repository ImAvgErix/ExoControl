"""Shared JSON HTTP for lease-free addon ops. Tests replace per-module hooks."""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Dict, Optional, Tuple


def request_json(
    method: str,
    url: str,
    headers: Dict[str, str],
    payload: Optional[Dict[str, Any]],
    timeout: float,
) -> Tuple[int, Dict[str, Any], str]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            status = int(getattr(resp, "status", 200) or 200)
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        return int(exc.code), _as_dict(raw), raw
    except urllib.error.URLError as exc:
        return 0, {"error": {"code": "CONNECT", "message": str(exc.reason or exc)}}, ""
    except TimeoutError as exc:
        return 0, {"error": {"code": "TIMEOUT", "message": str(exc)}}, ""
    loaded = _as_dict(raw)
    if raw and not loaded:
        try:
            val = json.loads(raw)
        except json.JSONDecodeError:
            return status, {}, raw
        if not isinstance(val, dict):
            return status, {"value": val}, raw
    return status, loaded, raw


def _as_dict(raw: str) -> Dict[str, Any]:
    if not raw:
        return {}
    try:
        loaded = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def error_from_http(status: int, parsed: Dict[str, Any], raw: str, *, what: str) -> Dict[str, Any]:
    err = parsed.get("error") if isinstance(parsed.get("error"), dict) else {}
    message = str(
        parsed.get("detail")
        or err.get("message")
        or parsed.get("message")
        or parsed.get("error")
        or ""
    ).strip()
    if isinstance(parsed.get("error"), str):
        message = parsed["error"].strip() or message
    if not message:
        message = raw[:240] if raw else f"{what} HTTP {status}"
    if status in {401, 403}:
        code = "AUTHENTICATION" if status == 401 else "FORBIDDEN"
    elif status == 429:
        code = "RATE_LIMIT"
    elif status in {400, 422}:
        code = "BAD_REQUEST"
    elif status == 404:
        code = "NOT_FOUND"
    elif status >= 500:
        code = "INTERNAL_SERVER"
    elif status == 0:
        code = str(err.get("code") or "CONNECT")
    else:
        code = "UNKNOWN"
    return {"ok": False, "error": message, "code": code, "http_status": status or None}


def timeout_of(step: Dict[str, Any], default: float = 30.0, hi: float = 60.0) -> float:
    try:
        return min(hi, max(2.0, float(step.get("timeout", default))))
    except (TypeError, ValueError):
        return default


def clip_int(value: Any, default: int, lo: int, hi: int) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, n))


def truncate(text: str, limit: int) -> str:
    if limit <= 0:
        return ""
    if len(text) <= limit:
        return text
    if limit <= 3:
        return text[:limit]
    return text[: limit - 3] + "..."


def env_key(*names: str) -> Optional[str]:
    import os

    for name in names:
        raw = (os.environ.get(name) or "").strip()
        if raw:
            return raw
    return None


def user_agent() -> str:
    from exo_control import __version__

    return f"exo-control/{__version__}"
