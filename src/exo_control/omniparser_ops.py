"""OmniParser — screenshot to structured clickable elements.

Local HTTP (``OMNIPARSER_URL``) or a test hook. No silent pixel spam.
"""
from __future__ import annotations

import base64
from pathlib import Path
from typing import Any, Dict, List, Optional

from exo_control.files_ops import _outside_denied, _resolve_under_roots
from exo_control.http_json import env_key, error_from_http, request_json, timeout_of, user_agent
from exo_control.policy import parse_confirm

_REQUEST_JSON = None
_PARSE = None


def service_url() -> Optional[str]:
    return env_key("OMNIPARSER_URL", "EXO_OMNIPARSER_URL")


def configured() -> bool:
    return bool(service_url()) or _PARSE is not None


def _call(method: str, url: str, headers: Dict[str, str], payload: Optional[Dict[str, Any]], timeout: float):
    if _REQUEST_JSON is not None:
        return _REQUEST_JSON(method, url, headers, payload, timeout)
    return request_json(method, url, headers, payload, timeout)


def parse(step: Dict[str, Any]) -> Dict[str, Any]:
    if _PARSE is None and not service_url():
        return {
            "ok": False,
            "error": "omni requires OMNIPARSER_URL or a local OmniParser server",
            "code": "UNAVAILABLE",
            "hint": "https://github.com/microsoft/OmniParser — run a local parse server and set OMNIPARSER_URL",
        }
    path = str(step.get("path") or step.get("image") or step.get("file") or "").strip()
    resolved = ""
    if path:
        ok, resolved_or_err, outside = _resolve_under_roots(path)
        if not ok:
            return {"ok": False, "error": resolved_or_err, "code": "BAD_PATH"}
        if outside:
            denied = _outside_denied("omni", resolved_or_err, parse_confirm(step.get("confirm", False)))
            if denied is not None:
                return denied
        resolved = resolved_or_err
        if not Path(resolved).is_file():
            return {"ok": False, "error": f"file not found: {resolved}", "code": "NOT_FOUND"}
    if _PARSE is not None:
        elements = _PARSE(step, resolved or path)
        return _view(elements, resolved or path)
    raw_b64 = str(step.get("image_b64") or step.get("b64") or "")
    if resolved and not raw_b64:
        raw_b64 = base64.b64encode(Path(resolved).read_bytes()).decode("ascii")
    if not raw_b64:
        return {"ok": False, "error": "omni requires path or image_b64", "code": "MISSING_IMAGE"}
    base = service_url().rstrip("/")
    payload = {"image": raw_b64, "path": resolved or None}
    status, parsed, raw = _call(
        "POST",
        f"{base}/parse",
        {"Content-Type": "application/json", "Accept": "application/json", "User-Agent": user_agent()},
        payload,
        timeout_of(step),
    )
    if status not in {200, 201}:
        return error_from_http(status, parsed, raw, what="omni")
    elements = parsed.get("elements") or parsed.get("parsed") or parsed.get("data") or []
    return _view(elements, resolved)


def _view(elements: Any, path: str) -> Dict[str, Any]:
    if not isinstance(elements, list):
        elements = []
    compact: List[Dict[str, Any]] = []
    for item in elements[:40]:
        if not isinstance(item, dict):
            continue
        compact.append({
            "label": item.get("label") or item.get("content") or item.get("name"),
            "x": item.get("x") or item.get("center_x"),
            "y": item.get("y") or item.get("center_y"),
            "bbox": item.get("bbox"),
        })
    return {
        "ok": True,
        "provider": "omniparser",
        "path": path or None,
        "elements": compact,
        "count": len(compact),
    }
