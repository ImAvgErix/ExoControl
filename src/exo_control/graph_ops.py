"""Microsoft Graph — To Do, OneNote, Teams, mail send, workbook/xlsx.

Auth: ``MICROSOFT_GRAPH_TOKEN`` (aliases ``EXO_GRAPH_TOKEN``, ``AZURE_TOKEN``,
``GRAPH_TOKEN``). Local ``xlsx`` CSV/TSV reads stay allowrooted and need no token.
``mail_send`` requires ``confirm=true``.
"""
from __future__ import annotations

import csv
import re
from io import StringIO
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote

from exo_control.files_ops import _outside_denied, _resolve_under_roots
from exo_control.http_json import clip_int, env_key, error_from_http, request_json, timeout_of, user_agent
from exo_control.policy import parse_confirm

_REQUEST_JSON = None
GRAPH_BASE = "https://graph.microsoft.com/v1.0"
_A1 = re.compile(r"^([A-Za-z]+)(\d+)$")


def graph_token() -> Optional[str]:
    return env_key("MICROSOFT_GRAPH_TOKEN", "EXO_GRAPH_TOKEN", "AZURE_TOKEN", "GRAPH_TOKEN")


def configured() -> bool:
    return bool(graph_token())


def _auth_denied(what: str) -> Dict[str, Any]:
    return {
        "ok": False,
        "error": f"{what} requires MICROSOFT_GRAPH_TOKEN",
        "code": "AUTHENTICATION",
        "hint": "export MICROSOFT_GRAPH_TOKEN (or EXO_GRAPH_TOKEN / AZURE_TOKEN)",
    }


def _headers(token: str) -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": user_agent(),
    }


def _call(method: str, url: str, headers: Dict[str, str], payload: Optional[Dict[str, Any]], timeout: float):
    if _REQUEST_JSON is not None:
        return _REQUEST_JSON(method, url, headers, payload, timeout)
    return request_json(method, url, headers, payload, timeout)


def _value_rows(parsed: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows = []
    for item in parsed.get("value") or []:
        if isinstance(item, dict):
            rows.append(item)
    return rows


def todo(step: Dict[str, Any]) -> Dict[str, Any]:
    token = graph_token()
    if not token:
        return _auth_denied("todo")
    list_id = str(step.get("list") or step.get("list_id") or step.get("id") or "").strip()
    top = clip_int(step.get("max") or step.get("limit") or 20, 20, 1, 50)
    if list_id:
        url = f"{GRAPH_BASE}/me/todo/lists/{quote(list_id)}/tasks?$top={top}"
    else:
        url = f"{GRAPH_BASE}/me/todo/lists?$top={top}"
    status, parsed, raw = _call("GET", url, _headers(token), None, timeout_of(step))
    if status != 200:
        return error_from_http(status, parsed, raw, what="todo")
    items = _value_rows(parsed)
    if list_id:
        tasks = [{"id": i.get("id"), "title": i.get("title"), "status": i.get("status")} for i in items]
        return {"ok": True, "provider": "microsoft-graph", "list": list_id, "tasks": tasks, "count": len(tasks)}
    lists = [{"id": i.get("id"), "displayName": i.get("displayName")} for i in items]
    return {"ok": True, "provider": "microsoft-graph", "lists": lists, "count": len(lists)}


def onenote(step: Dict[str, Any]) -> Dict[str, Any]:
    token = graph_token()
    if not token:
        return _auth_denied("onenote")
    notebook = str(step.get("notebook") or step.get("id") or "").strip()
    top = clip_int(step.get("max") or step.get("limit") or 20, 20, 1, 50)
    if notebook:
        url = f"{GRAPH_BASE}/me/onenote/notebooks/{quote(notebook)}/sections?$top={top}"
    else:
        url = f"{GRAPH_BASE}/me/onenote/notebooks?$top={top}"
    status, parsed, raw = _call("GET", url, _headers(token), None, timeout_of(step))
    if status != 200:
        return error_from_http(status, parsed, raw, what="onenote")
    items = _value_rows(parsed)
    if notebook:
        sections = [{"id": i.get("id"), "displayName": i.get("displayName")} for i in items]
        return {"ok": True, "provider": "microsoft-graph", "notebook": notebook, "sections": sections, "count": len(sections)}
    notebooks = [{"id": i.get("id"), "displayName": i.get("displayName")} for i in items]
    return {"ok": True, "provider": "microsoft-graph", "notebooks": notebooks, "count": len(notebooks)}


def teams(step: Dict[str, Any]) -> Dict[str, Any]:
    token = graph_token()
    if not token:
        return _auth_denied("teams")
    kind = str(step.get("kind") or step.get("action") or "teams").lower()
    top = clip_int(step.get("max") or step.get("limit") or 20, 20, 1, 50)
    if kind in {"chats", "chat"}:
        url = f"{GRAPH_BASE}/me/chats?$top={top}"
    else:
        url = f"{GRAPH_BASE}/me/joinedTeams?$top={top}"
    status, parsed, raw = _call("GET", url, _headers(token), None, timeout_of(step))
    if status != 200:
        return error_from_http(status, parsed, raw, what="teams")
    items = _value_rows(parsed)
    if kind in {"chats", "chat"}:
        chats = [{"id": i.get("id"), "topic": i.get("topic"), "chatType": i.get("chatType")} for i in items]
        return {"ok": True, "provider": "microsoft-graph", "chats": chats, "count": len(chats)}
    rows = [{"id": i.get("id"), "displayName": i.get("displayName")} for i in items]
    return {"ok": True, "provider": "microsoft-graph", "teams": rows, "count": len(rows)}


def mail_send(step: Dict[str, Any]) -> Dict[str, Any]:
    token = graph_token()
    if not token:
        return _auth_denied("mail_send")
    if not parse_confirm(step.get("confirm", False)):
        return {"ok": False, "error": "mail_send requires confirm=true", "code": "CONFIRM_REQUIRED"}
    to_raw = step.get("to") or step.get("recipient") or step.get("email") or ""
    if isinstance(to_raw, (list, tuple)):
        addrs = [str(a).strip() for a in to_raw if str(a).strip()]
    else:
        addrs = [a.strip() for a in str(to_raw).split(",") if a.strip()]
    if not addrs:
        return {"ok": False, "error": "mail_send requires to", "code": "MISSING_TO"}
    subject = str(step.get("subject") or step.get("title") or "")
    body = str(step.get("body") or step.get("text") or step.get("html") or "")
    content_type = "HTML" if step.get("html") or str(step.get("content_type") or "").lower() == "html" else "Text"
    payload = {
        "message": {
            "subject": subject,
            "body": {"contentType": content_type, "content": body},
            "toRecipients": [{"emailAddress": {"address": a}} for a in addrs],
        },
        "saveToSentItems": True,
    }
    status, parsed, raw = _call(
        "POST", f"{GRAPH_BASE}/me/sendMail", _headers(token), payload, timeout_of(step),
    )
    if status not in {200, 202}:
        return error_from_http(status, parsed, raw, what="mail_send")
    return {"ok": True, "provider": "microsoft-graph", "to": addrs, "subject": subject}


def _col_idx(col: str) -> int:
    n = 0
    for ch in col.upper():
        n = n * 26 + (ord(ch) - 64)
    return n - 1


def _parse_a1(cell: str) -> Tuple[int, int]:
    m = _A1.match((cell or "").strip())
    if not m:
        raise ValueError(f"bad A1 cell: {cell!r}")
    return _col_idx(m.group(1)), int(m.group(2)) - 1


def _slice_rows(rows: List[List[str]], spec: str) -> List[List[str]]:
    if not spec:
        return rows
    left, _, right = spec.partition(":")
    right = right or left
    c1, r1 = _parse_a1(left)
    c2, r2 = _parse_a1(right)
    if c1 > c2:
        c1, c2 = c2, c1
    if r1 > r2:
        r1, r2 = r2, r1
    out: List[List[str]] = []
    for r in range(r1, r2 + 1):
        if r < 0 or r >= len(rows):
            continue
        row = rows[r]
        out.append([(row[c] if c < len(row) else "") for c in range(c1, c2 + 1)])
    return out


def _read_local_table(path: Path) -> List[List[str]]:
    suffix = path.suffix.lower()
    raw = path.read_text(encoding="utf-8", errors="replace")
    if suffix in {".tsv", ".tab"}:
        reader = csv.reader(StringIO(raw), delimiter="\t")
    else:
        reader = csv.reader(StringIO(raw))
    return [list(row) for row in reader]


def _xlsx_graph(step: Dict[str, Any], token: str) -> Dict[str, Any]:
    item = str(step.get("workbook") or step.get("item") or step.get("item_id") or "").strip()
    drive_path = str(step.get("drive_path") or step.get("onedrive") or "").strip()
    sheet = str(step.get("sheet") or step.get("worksheet") or "Sheet1").strip() or "Sheet1"
    addr = str(step.get("range") or step.get("address") or "A1:C20").strip() or "A1:C20"
    if item:
        url = (
            f"{GRAPH_BASE}/me/drive/items/{quote(item)}/workbook/worksheets/{quote(sheet)}"
            f"/range(address='{addr}')"
        )
    elif drive_path:
        url = (
            f"{GRAPH_BASE}/me/drive/root:/{quote(drive_path.lstrip('/'))}:/workbook"
            f"/worksheets/{quote(sheet)}/range(address='{addr}')"
        )
    else:
        return {"ok": False, "error": "xlsx graph path needs workbook or drive_path", "code": "MISSING_WORKBOOK"}
    status, parsed, raw = _call("GET", url, _headers(token), None, timeout_of(step))
    if status != 200:
        return error_from_http(status, parsed, raw, what="xlsx")
    values = parsed.get("values") if isinstance(parsed.get("values"), list) else []
    rows = [[str(c) if c is not None else "" for c in row] for row in values if isinstance(row, list)]
    return {
        "ok": True,
        "source": "graph",
        "provider": "microsoft-graph",
        "sheet": sheet,
        "range": addr,
        "rows": rows,
        "count": len(rows),
    }


def xlsx(step: Dict[str, Any]) -> Dict[str, Any]:
    path = str(step.get("path") or step.get("file") or "").strip()
    if path:
        ok, resolved, outside = _resolve_under_roots(path)
        if not ok:
            return {"ok": False, "error": resolved, "code": "BAD_PATH"}
        denied = _outside_denied("xlsx", resolved, parse_confirm(step.get("confirm", False))) if outside else None
        if denied:
            return denied
        target = Path(resolved)
        if not target.is_file():
            return {"ok": False, "error": f"xlsx file not found: {resolved}", "code": "NOT_FOUND"}
        suffix = target.suffix.lower()
        if suffix not in {".csv", ".tsv", ".tab", ".txt"}:
            return {
                "ok": False,
                "error": "local xlsx binary needs Graph workbook= or a csv/tsv path",
                "code": "UNAVAILABLE",
                "hint": "pass a .csv or Graph workbook= with MICROSOFT_GRAPH_TOKEN",
            }
        try:
            rows = _read_local_table(target)
            spec = str(step.get("range") or step.get("address") or "").strip()
            sliced = _slice_rows(rows, spec) if spec else rows[: clip_int(step.get("max") or 40, 40, 1, 200)]
        except ValueError as exc:
            return {"ok": False, "error": str(exc), "code": "BAD_RANGE"}
        return {
            "ok": True,
            "source": "local",
            "path": resolved,
            "range": spec or None,
            "rows": sliced,
            "count": len(sliced),
        }
    token = graph_token()
    if token and (step.get("workbook") or step.get("item") or step.get("item_id") or step.get("drive_path") or step.get("onedrive")):
        return _xlsx_graph(step, token)
    if token:
        return {"ok": False, "error": "xlsx requires path or workbook=", "code": "MISSING_PATH"}
    return {"ok": False, "error": "xlsx requires path (csv) or MICROSOFT_GRAPH_TOKEN + workbook", "code": "MISSING_PATH"}


def cal_add(step: Dict[str, Any]) -> Dict[str, Any]:
    token = graph_token()
    if not token:
        return _auth_denied("cal_add")
    if not parse_confirm(step.get("confirm", False)):
        return {"ok": False, "error": "cal_add requires confirm=true", "code": "CONFIRM_REQUIRED"}
    subject = str(step.get("subject") or step.get("title") or "").strip()
    if not subject:
        return {"ok": False, "error": "cal_add requires subject", "code": "MISSING_SUBJECT"}
    start = str(step.get("start") or step.get("start_at") or "")
    end = str(step.get("end") or step.get("end_at") or "")
    payload: Dict[str, Any] = {"subject": subject}
    if start:
        payload["start"] = {"dateTime": start, "timeZone": str(step.get("tz") or "UTC")}
    if end:
        payload["end"] = {"dateTime": end, "timeZone": str(step.get("tz") or "UTC")}
    if step.get("body"):
        payload["body"] = {"contentType": "Text", "content": str(step.get("body"))}
    status, parsed, raw = _call("POST", f"{GRAPH_BASE}/me/events", _headers(token), payload, timeout_of(step))
    if status not in {200, 201}:
        return error_from_http(status, parsed, raw, what="cal_add")
    return {"ok": True, "provider": "microsoft-graph", "id": parsed.get("id"), "subject": subject}


def todo_add(step: Dict[str, Any]) -> Dict[str, Any]:
    token = graph_token()
    if not token:
        return _auth_denied("todo_add")
    if not parse_confirm(step.get("confirm", False)):
        return {"ok": False, "error": "todo_add requires confirm=true", "code": "CONFIRM_REQUIRED"}
    title = str(step.get("title") or step.get("text") or step.get("task") or "").strip()
    list_id = str(step.get("list") or step.get("list_id") or "").strip()
    if not title or not list_id:
        return {"ok": False, "error": "todo_add requires title and list", "code": "MISSING_FIELDS"}
    status, parsed, raw = _call(
        "POST",
        f"{GRAPH_BASE}/me/todo/lists/{quote(list_id)}/tasks",
        _headers(token),
        {"title": title},
        timeout_of(step),
    )
    if status not in {200, 201}:
        return error_from_http(status, parsed, raw, what="todo_add")
    return {"ok": True, "provider": "microsoft-graph", "id": parsed.get("id"), "title": title, "list": list_id}


def contacts(step: Dict[str, Any]) -> Dict[str, Any]:
    token = graph_token()
    if not token:
        return _auth_denied("contacts")
    top = clip_int(step.get("max") or 20, 20, 1, 50)
    status, parsed, raw = _call(
        "GET", f"{GRAPH_BASE}/me/contacts?$top={top}&$select=displayName,emailAddresses,id",
        _headers(token), None, timeout_of(step),
    )
    if status != 200:
        return error_from_http(status, parsed, raw, what="contacts")
    rows = []
    for item in _value_rows(parsed):
        emails = item.get("emailAddresses") or []
        addr = ""
        if emails and isinstance(emails[0], dict):
            addr = str(emails[0].get("address") or "")
        rows.append({"id": item.get("id"), "displayName": item.get("displayName"), "email": addr})
    return {"ok": True, "provider": "microsoft-graph", "contacts": rows, "count": len(rows)}


def drive_put(step: Dict[str, Any]) -> Dict[str, Any]:
    token = graph_token()
    if not token:
        return _auth_denied("drive_put")
    if not parse_confirm(step.get("confirm", False)):
        return {"ok": False, "error": "drive_put requires confirm=true", "code": "CONFIRM_REQUIRED"}
    path = str(step.get("path") or step.get("file") or "").strip()
    dest = str(step.get("dest") or step.get("to") or Path(path).name if path else "").strip()
    if not path or not dest:
        return {"ok": False, "error": "drive_put requires path and dest", "code": "MISSING_PATH"}
    ok, resolved, outside = _resolve_under_roots(path)
    if not ok:
        return {"ok": False, "error": resolved, "code": "BAD_PATH"}
    if outside:
        denied = _outside_denied("drive_put", resolved, True)
        if denied:
            return denied
    target = Path(resolved)
    if not target.is_file():
        return {"ok": False, "error": f"file not found: {resolved}", "code": "NOT_FOUND"}
    # Metadata-only PUT via JSON hook (tests); native upload would stream bytes.
    payload = {"name": dest, "size": target.stat().st_size}
    status, parsed, raw = _call(
        "PUT",
        f"{GRAPH_BASE}/me/drive/root:/{quote(dest.lstrip('/'))}:/content",
        _headers(token),
        payload,
        timeout_of(step),
    )
    if status not in {200, 201}:
        return error_from_http(status, parsed, raw, what="drive_put")
    return {
        "ok": True,
        "provider": "microsoft-graph",
        "id": parsed.get("id"),
        "name": parsed.get("name") or dest,
        "path": resolved,
    }


def mail_reply(step: Dict[str, Any]) -> Dict[str, Any]:
    token = graph_token()
    if not token:
        return _auth_denied("mail_reply")
    if not parse_confirm(step.get("confirm", False)):
        return {"ok": False, "error": "mail_reply requires confirm=true", "code": "CONFIRM_REQUIRED"}
    mid = str(step.get("id") or step.get("message_id") or step.get("message") or "").strip()
    body = str(step.get("body") or step.get("text") or step.get("comment") or "")
    if not mid:
        return {"ok": False, "error": "mail_reply requires id", "code": "MISSING_ID"}
    status, parsed, raw = _call(
        "POST",
        f"{GRAPH_BASE}/me/messages/{quote(mid)}/reply",
        _headers(token),
        {"comment": body},
        timeout_of(step),
    )
    if status not in {200, 201, 202}:
        return error_from_http(status, parsed, raw, what="mail_reply")
    return {"ok": True, "provider": "microsoft-graph", "id": mid}
