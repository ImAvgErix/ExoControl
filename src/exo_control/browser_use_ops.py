"""Browser Use Cloud — hosted runs + managed Chromium (CDP).

Does not vendor the ``browser-use`` agent loop. HTTP against API v4:
https://api.browser-use.com/api/v4

Auth: ``BROWSER_USE_API_KEY`` (alias ``EXO_BROWSER_USE_API_KEY``).
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any, Dict, Optional, Tuple


BASE_URL = "https://api.browser-use.com/api/v4"
DEFAULT_TIMEOUT = 30.0
MAX_TIMEOUT = 60.0
DEFAULT_POLL = 1.5

# Tests replace this.
_REQUEST_JSON = None


def api_key() -> Optional[str]:
    from exo_control.policy import browser_use_api_key

    return browser_use_api_key() or None


def configured() -> bool:
    return bool(api_key())


def _auth_denied() -> Dict[str, Any]:
    return {
        "ok": False,
        "error": "browser_use requires BROWSER_USE_API_KEY",
        "code": "AUTHENTICATION",
        "hint": "export BROWSER_USE_API_KEY from https://cloud.browser-use.com/settings?tab=api-keys",
    }


def _headers(key: str) -> Dict[str, str]:
    from exo_control import __version__

    return {
        "X-Browser-Use-API-Key": key,
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": f"exo-control/{__version__}",
    }


def _request_json(
    method: str,
    url: str,
    headers: Dict[str, str],
    payload: Optional[Dict[str, Any]],
    timeout: float,
) -> Tuple[int, Dict[str, Any], str]:
    if _REQUEST_JSON is not None:
        return _REQUEST_JSON(method, url, headers, payload, timeout)
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            status = int(getattr(resp, "status", 200) or 200)
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        parsed: Dict[str, Any] = {}
        if raw:
            try:
                loaded = json.loads(raw)
                if isinstance(loaded, dict):
                    parsed = loaded
            except json.JSONDecodeError:
                parsed = {}
        return int(exc.code), parsed, raw
    except urllib.error.URLError as exc:
        return 0, {"error": {"code": "CONNECT", "message": str(exc.reason or exc)}}, ""
    except TimeoutError as exc:
        return 0, {"error": {"code": "TIMEOUT", "message": str(exc)}}, ""
    try:
        loaded = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        return status, {}, raw
    if not isinstance(loaded, dict):
        return status, {"value": loaded}, raw
    return status, loaded, raw


def _error_from_http(status: int, parsed: Dict[str, Any], raw: str) -> Dict[str, Any]:
    detail = parsed.get("detail")
    if isinstance(detail, str) and detail.strip():
        message = detail.strip()
    else:
        err = parsed.get("error") if isinstance(parsed.get("error"), dict) else {}
        message = str(err.get("message") or parsed.get("message") or "").strip()
    if not message:
        message = raw[:240] if raw else f"browser_use HTTP {status}"
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
        code = str((parsed.get("error") or {}).get("code") or "CONNECT")
    else:
        code = "UNKNOWN"
    return {"ok": False, "error": message, "code": code, "http_status": status or None}


def _timeout(step: Dict[str, Any], default: float = DEFAULT_TIMEOUT) -> float:
    try:
        return min(MAX_TIMEOUT, max(2.0, float(step.get("timeout", default))))
    except (TypeError, ValueError):
        return default


def _pick(parsed: Dict[str, Any], *names: str) -> Any:
    for name in names:
        if name in parsed and parsed[name] is not None:
            return parsed[name]
    return None


def _session_view(parsed: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "ok": True,
        "provider": "browser-use",
        "id": _pick(parsed, "id"),
        "status": _pick(parsed, "status"),
        "cdp_url": _pick(parsed, "cdpUrl", "cdp_url"),
        "live_url": _pick(parsed, "liveUrl", "live_url"),
        "timeout_at": _pick(parsed, "timeoutAt", "timeout_at"),
    }


def start_browser(step: Dict[str, Any]) -> Dict[str, Any]:
    key = api_key()
    if not key:
        return _auth_denied()
    country = step.get("country") or step.get("proxy_country") or step.get("proxyCountryCode") or "us"
    payload: Dict[str, Any] = {}
    if country is not None and str(country).strip().lower() not in {"", "none", "null", "off"}:
        payload["proxyCountryCode"] = str(country).strip().lower()
    else:
        payload["proxyCountryCode"] = None
    timeout_min = step.get("session_timeout") or step.get("session_minutes")
    if timeout_min is not None:
        try:
            payload["timeout"] = max(1, min(240, int(timeout_min)))
        except (TypeError, ValueError):
            pass
    profile = step.get("profile_id") or step.get("profileId")
    if profile:
        payload["profileId"] = str(profile)
    if step.get("record") is True or step.get("enableRecording") is True:
        payload["enableRecording"] = True
    status, parsed, raw = _request_json(
        "POST", f"{BASE_URL}/browsers", _headers(key), payload, _timeout(step)
    )
    if status not in {200, 201}:
        return _error_from_http(status, parsed, raw)
    return _session_view(parsed)


def stop_browser(step: Dict[str, Any], *, default_id: Optional[str] = None) -> Dict[str, Any]:
    key = api_key()
    if not key:
        return _auth_denied()
    sid = str(step.get("id") or step.get("session_id") or step.get("browser_id") or default_id or "").strip()
    if not sid:
        return {"ok": False, "error": "browser_use_stop requires id", "code": "MISSING_ID"}
    status, parsed, raw = _request_json(
        "PATCH",
        f"{BASE_URL}/browsers/{sid}",
        _headers(key),
        {"action": "stop"},
        _timeout(step),
    )
    if status not in {200, 201, 204}:
        return _error_from_http(status, parsed, raw)
    out = _session_view(parsed) if parsed else {"ok": True, "provider": "browser-use", "id": sid}
    out["ok"] = True
    out["id"] = sid
    out["stopped"] = True
    return out


def _compact_run(parsed: Dict[str, Any], *, verbose: bool) -> Dict[str, Any]:
    output = _pick(parsed, "output", "result", "text", "answer")
    if isinstance(output, str) and not verbose and len(output) > 1200:
        output = output[:1197] + "..."
    return {
        "ok": True,
        "provider": "browser-use",
        "run_id": _pick(parsed, "id", "runId", "run_id"),
        "session_id": _pick(parsed, "sessionId", "session_id"),
        "status": _pick(parsed, "status"),
        "output": output,
    }


def _is_terminal(status: Any) -> bool:
    return str(status or "").strip().lower() in {"completed", "failed", "cancelled", "canceled", "error"}


def run_task(step: Dict[str, Any]) -> Dict[str, Any]:
    """Create a hosted run, or poll an existing ``run_id``."""
    key = api_key()
    if not key:
        return _auth_denied()
    headers = _headers(key)
    timeout = _timeout(step)
    verbose = step.get("verbose") is True
    run_id = str(step.get("run_id") or step.get("id") or "").strip()
    if run_id:
        status, parsed, raw = _request_json(
            "GET", f"{BASE_URL}/runs/{run_id}", headers, None, timeout
        )
        if status != 200:
            st_status, st_parsed, st_raw = _request_json(
                "GET", f"{BASE_URL}/runs/{run_id}/status", headers, None, timeout
            )
            if st_status != 200:
                return _error_from_http(status, parsed, raw)
            parsed = st_parsed
        out = _compact_run(parsed, verbose=verbose)
        out["run_id"] = out.get("run_id") or run_id
        return out

    task = step.get("task") or step.get("text") or step.get("query") or step.get("prompt")
    if not str(task or "").strip():
        return {"ok": False, "error": "browser_use requires task or run_id", "code": "MISSING_TASK"}
    payload: Dict[str, Any] = {"task": str(task).strip()}
    session = step.get("session_id") or step.get("sessionId")
    if session:
        payload["sessionId"] = str(session)
    status, parsed, raw = _request_json("POST", f"{BASE_URL}/runs", headers, payload, timeout)
    if status not in {200, 201}:
        return _error_from_http(status, parsed, raw)
    out = _compact_run(parsed, verbose=verbose)
    wait = step.get("wait") is True
    rid = out.get("run_id")
    if not wait or not rid:
        return out
    deadline = time.time() + timeout
    poll = max(0.4, float(step.get("poll", DEFAULT_POLL)))
    while time.time() < deadline and not _is_terminal(out.get("status")):
        time.sleep(min(poll, max(0.0, deadline - time.time())))
        st, body, _raw = _request_json("GET", f"{BASE_URL}/runs/{rid}/status", headers, None, timeout)
        if st != 200:
            break
        out = _compact_run(body, verbose=verbose)
        out["run_id"] = out.get("run_id") or rid
    if _is_terminal(out.get("status")):
        st, body, _raw = _request_json("GET", f"{BASE_URL}/runs/{rid}", headers, None, timeout)
        if st == 200:
            out = _compact_run(body, verbose=verbose)
            out["run_id"] = out.get("run_id") or rid
    out["waited"] = True
    return out

