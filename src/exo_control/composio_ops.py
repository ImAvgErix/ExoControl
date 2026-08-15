"""Composio + Microsoft Graph — mail/calendar/drive without clicking Outlook.

Auth: ``COMPOSIO_API_KEY`` and/or ``MICROSOFT_GRAPH_TOKEN``
(aliases ``EXO_COMPOSIO_API_KEY``, ``EXO_GRAPH_TOKEN``, ``AZURE_TOKEN``).
Send/delete-style Composio actions need ``confirm=true``.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
from urllib.parse import quote

from exo_control.http_json import clip_int, env_key, error_from_http, request_json, timeout_of, user_agent
from exo_control.policy import parse_confirm

_REQUEST_JSON = None
COMPOSIO_BASE = "https://backend.composio.dev/api/v2"
GRAPH_BASE = "https://graph.microsoft.com/v1.0"
_MUTATE_TOKENS = (
    "SEND", "DELETE", "CREATE", "UPDATE", "REPLY", "TRASH", "REMOVE",
    "WRITE", "PUT", "MOVE", "DRAFT_SEND", "CANCEL",
)


def composio_key() -> Optional[str]:
    return env_key("COMPOSIO_API_KEY", "EXO_COMPOSIO_API_KEY")


def graph_token() -> Optional[str]:
    return env_key("MICROSOFT_GRAPH_TOKEN", "EXO_GRAPH_TOKEN", "AZURE_TOKEN")


def configured() -> bool:
    return bool(composio_key() or graph_token())


def _auth_denied(what: str = "composio") -> Dict[str, Any]:
    return {
        "ok": False,
        "error": f"{what} requires COMPOSIO_API_KEY or MICROSOFT_GRAPH_TOKEN",
        "code": "AUTHENTICATION",
        "hint": "export COMPOSIO_API_KEY or MICROSOFT_GRAPH_TOKEN",
    }


def _call(method: str, url: str, headers: Dict[str, str], payload: Optional[Dict[str, Any]], timeout: float):
    if _REQUEST_JSON is not None:
        return _REQUEST_JSON(method, url, headers, payload, timeout)
    return request_json(method, url, headers, payload, timeout)


def _is_mutating(action: str) -> bool:
    up = (action or "").upper()
    return any(tok in up for tok in _MUTATE_TOKENS)


def run(step: Dict[str, Any]) -> Dict[str, Any]:
    key = composio_key()
    if not key:
        return _auth_denied("composio")
    action = str(step.get("action") or step.get("tool") or step.get("name") or "").strip()
    if not action:
        return {"ok": False, "error": "composio requires action", "code": "MISSING_ACTION"}
    if _is_mutating(action) and not parse_confirm(step.get("confirm", False)):
        return {"ok": False, "error": "composio mutating action requires confirm=true", "code": "CONFIRM_REQUIRED"}
    payload = {"input": step.get("input") or step.get("params") or {}}
    if not isinstance(payload["input"], dict):
        payload["input"] = {"value": payload["input"]}
    entity = step.get("entity_id") or step.get("entityId")
    if entity:
        payload["entityId"] = str(entity)
    url = f"{(os.environ.get('COMPOSIO_API_URL') or COMPOSIO_BASE).rstrip('/')}/actions/{action}/execute"
    status, parsed, raw = _call(
        "POST",
        url,
        {
            "x-api-key": key,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": user_agent(),
        },
        payload,
        timeout_of(step),
    )
    if status not in {200, 201}:
        return error_from_http(status, parsed, raw, what="composio")
    return {
        "ok": True,
        "provider": "composio",
        "action": action,
        "data": parsed.get("data") if "data" in parsed else parsed,
    }


def _graph_headers(token: str) -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "User-Agent": user_agent(),
    }


def mail_list(step: Dict[str, Any]) -> Dict[str, Any]:
    token = graph_token()
    if token:
        top = clip_int(step.get("max") or step.get("limit") or 5, 5, 1, 25)
        url = f"{GRAPH_BASE}/me/messages?$top={top}&$select=subject,from,receivedDateTime"
        status, parsed, raw = _call("GET", url, _graph_headers(token), None, timeout_of(step))
        if status != 200:
            return error_from_http(status, parsed, raw, what="mail_list")
        rows = []
        for item in parsed.get("value") or []:
            if not isinstance(item, dict):
                continue
            frm = item.get("from") or {}
            addr = ""
            if isinstance(frm, dict):
                addr = str((frm.get("emailAddress") or {}).get("address") or frm.get("address") or "")
            rows.append({
                "subject": item.get("subject"),
                "from": addr,
                "received": item.get("receivedDateTime"),
            })
        return {"ok": True, "provider": "microsoft-graph", "messages": rows, "count": len(rows)}
    if composio_key():
        return run({**step, "action": "GMAIL_FETCH_EMAILS", "confirm": False})
    return _auth_denied("mail_list")


def cal_next(step: Dict[str, Any]) -> Dict[str, Any]:
    token = graph_token()
    if token:
        top = clip_int(step.get("max") or step.get("limit") or 5, 5, 1, 25)
        start = datetime.now(timezone.utc)
        end = start + timedelta(days=7)
        url = (
            f"{GRAPH_BASE}/me/calendarView?startDateTime={start.strftime('%Y-%m-%dT%H:%M:%SZ')}"
            f"&endDateTime={end.strftime('%Y-%m-%dT%H:%M:%SZ')}&$top={top}&$orderby=start/dateTime"
        )
        status, parsed, raw = _call("GET", url, _graph_headers(token), None, timeout_of(step))
        if status != 200:
            return error_from_http(status, parsed, raw, what="cal_next")
        rows = []
        for item in parsed.get("value") or []:
            if not isinstance(item, dict):
                continue
            start_at = item.get("start") or {}
            rows.append({
                "subject": item.get("subject"),
                "start": start_at.get("dateTime") if isinstance(start_at, dict) else start_at,
            })
        return {"ok": True, "provider": "microsoft-graph", "events": rows, "count": len(rows)}
    if composio_key():
        return run({**step, "action": "GOOGLECALENDAR_FIND_EVENT", "confirm": False})
    return _auth_denied("cal_next")


def drive_get(step: Dict[str, Any]) -> Dict[str, Any]:
    token = graph_token()
    path = str(step.get("path") or step.get("item") or step.get("name") or "").strip()
    if token:
        if path:
            url = f"{GRAPH_BASE}/me/drive/root:/{quote(path.lstrip('/'))}"
        else:
            url = f"{GRAPH_BASE}/me/drive/root/children?$top={clip_int(step.get('max') or 10, 10, 1, 40)}"
        status, parsed, raw = _call("GET", url, _graph_headers(token), None, timeout_of(step))
        if status != 200:
            return error_from_http(status, parsed, raw, what="drive_get")
        if path:
            return {
                "ok": True,
                "provider": "microsoft-graph",
                "name": parsed.get("name"),
                "id": parsed.get("id"),
                "web_url": parsed.get("webUrl"),
                "size": parsed.get("size"),
            }
        items = []
        for item in parsed.get("value") or []:
            if isinstance(item, dict):
                items.append({"name": item.get("name"), "id": item.get("id"), "folder": "folder" in item})
        return {"ok": True, "provider": "microsoft-graph", "items": items, "count": len(items)}
    if composio_key():
        if not path:
            return {"ok": False, "error": "drive_get requires path", "code": "MISSING_PATH"}
        return run({**step, "action": "ONEDRIVE_GET_ITEM", "input": {"path": path}, "confirm": False})
    return _auth_denied("drive_get")
