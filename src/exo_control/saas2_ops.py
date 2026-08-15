"""More SaaS HTTP: Jira, Discord, Airtable, Trello, Asana, Telegram, Serper, Brave."""
from __future__ import annotations

import base64
import os
from typing import Any, Dict, Optional
from urllib.parse import quote, urlencode

from exo_control.http_json import clip_int, env_key, error_from_http, request_json, timeout_of, user_agent
from exo_control.policy import parse_confirm

_REQUEST_JSON = None


def _call(method: str, url: str, headers: Dict[str, str], payload: Optional[Dict[str, Any]], timeout: float):
    if _REQUEST_JSON is not None:
        return _REQUEST_JSON(method, url, headers, payload, timeout)
    return request_json(method, url, headers, payload, timeout)


def _auth(what: str, env: str) -> Dict[str, Any]:
    return {"ok": False, "error": f"{what} requires {env}", "code": "AUTHENTICATION", "hint": f"export {env}"}


def _ua() -> Dict[str, str]:
    return {"Accept": "application/json", "Content-Type": "application/json", "User-Agent": user_agent()}


def jira_configured() -> bool:
    return bool(env_key("JIRA_API_TOKEN", "EXO_JIRA_API_TOKEN") and env_key("JIRA_BASE", "EXO_JIRA_BASE"))


def discord_configured() -> bool:
    return bool(env_key("DISCORD_BOT_TOKEN", "EXO_DISCORD_BOT_TOKEN"))


def jira(step: Dict[str, Any]) -> Dict[str, Any]:
    base = (env_key("JIRA_BASE", "EXO_JIRA_BASE") or "").rstrip("/")
    email = env_key("JIRA_EMAIL", "EXO_JIRA_EMAIL") or ""
    token = env_key("JIRA_API_TOKEN", "EXO_JIRA_API_TOKEN")
    if not base or not token:
        return _auth("jira", "JIRA_BASE and JIRA_API_TOKEN")
    jql = str(step.get("jql") or step.get("query") or step.get("q") or "order by updated DESC").strip()
    raw_auth = f"{email}:{token}".encode("utf-8") if email else token.encode("utf-8")
    headers = {
        **_ua(),
        "Authorization": "Basic " + base64.b64encode(raw_auth).decode("ascii") if email else f"Bearer {token}",
    }
    url = f"{base}/rest/api/3/search?" + urlencode({"jql": jql, "maxResults": clip_int(step.get("max") or 10, 10, 1, 30)})
    status, parsed, raw = _call("GET", url, headers, None, timeout_of(step))
    if status != 200:
        return error_from_http(status, parsed, raw, what="jira")
    issues = []
    for item in parsed.get("issues") or []:
        if isinstance(item, dict):
            fields = item.get("fields") if isinstance(item.get("fields"), dict) else {}
            issues.append({"key": item.get("key"), "summary": fields.get("summary")})
    return {"ok": True, "provider": "jira", "issues": issues, "count": len(issues)}


def discord(step: Dict[str, Any]) -> Dict[str, Any]:
    token = env_key("DISCORD_BOT_TOKEN", "EXO_DISCORD_BOT_TOKEN")
    if not token:
        return _auth("discord", "DISCORD_BOT_TOKEN")
    headers = {**_ua(), "Authorization": f"Bot {token}"}
    channel = str(step.get("channel") or step.get("channel_id") or "").strip()
    text = str(step.get("text") or step.get("message") or "").strip()
    if text and channel:
        if not parse_confirm(step.get("confirm", False)):
            return {"ok": False, "error": "discord post requires confirm=true", "code": "CONFIRM_REQUIRED"}
        status, parsed, raw = _call(
            "POST", f"https://discord.com/api/v10/channels/{quote(channel)}/messages",
            headers, {"content": text}, timeout_of(step),
        )
        if status not in {200, 201}:
            return error_from_http(status, parsed, raw, what="discord")
        return {"ok": True, "provider": "discord", "id": parsed.get("id")}
    status, parsed, raw = _call("GET", "https://discord.com/api/v10/users/@me", headers, None, timeout_of(step))
    if status != 200:
        return error_from_http(status, parsed, raw, what="discord")
    return {"ok": True, "provider": "discord", "id": parsed.get("id"), "username": parsed.get("username")}


def airtable(step: Dict[str, Any]) -> Dict[str, Any]:
    key = env_key("AIRTABLE_API_KEY", "EXO_AIRTABLE_API_KEY")
    if not key:
        return _auth("airtable", "AIRTABLE_API_KEY")
    base = str(step.get("base") or step.get("base_id") or os.environ.get("AIRTABLE_BASE") or "").strip()
    table = str(step.get("table") or step.get("table_id") or "").strip()
    if not base or not table:
        return {"ok": False, "error": "airtable requires base and table", "code": "MISSING_FIELDS"}
    url = f"https://api.airtable.com/v0/{quote(base)}/{quote(table)}?maxRecords={clip_int(step.get('max') or 10, 10, 1, 40)}"
    status, parsed, raw = _call("GET", url, {**_ua(), "Authorization": f"Bearer {key}"}, None, timeout_of(step))
    if status != 200:
        return error_from_http(status, parsed, raw, what="airtable")
    records = [r for r in (parsed.get("records") or []) if isinstance(r, dict)]
    return {"ok": True, "provider": "airtable", "records": [{"id": r.get("id")} for r in records], "count": len(records)}


def trello(step: Dict[str, Any]) -> Dict[str, Any]:
    key = env_key("TRELLO_KEY", "TRELLO_API_KEY", "EXO_TRELLO_KEY")
    token = env_key("TRELLO_TOKEN", "EXO_TRELLO_TOKEN")
    if not key or not token:
        return _auth("trello", "TRELLO_KEY and TRELLO_TOKEN")
    url = f"https://api.trello.com/1/members/me/boards?key={quote(key)}&token={quote(token)}"
    status, parsed, raw = _call("GET", url, _ua(), None, timeout_of(step))
    if status != 200:
        return error_from_http(status, parsed, raw, what="trello")
    items = parsed.get("value") if isinstance(parsed.get("value"), list) else parsed
    if not isinstance(items, list):
        items = []
    boards = [{"id": i.get("id"), "name": i.get("name")} for i in items if isinstance(i, dict)]
    return {"ok": True, "provider": "trello", "boards": boards, "count": len(boards)}


def asana(step: Dict[str, Any]) -> Dict[str, Any]:
    token = env_key("ASANA_ACCESS_TOKEN", "ASANA_TOKEN", "EXO_ASANA_TOKEN")
    if not token:
        return _auth("asana", "ASANA_ACCESS_TOKEN")
    url = "https://app.asana.com/api/1.0/tasks?opt_fields=name,gid&limit=" + str(clip_int(step.get("max") or 10, 10, 1, 30))
    workspace = str(step.get("workspace") or os.environ.get("ASANA_WORKSPACE") or "").strip()
    if workspace:
        url += f"&workspace={quote(workspace)}"
    assignee = str(step.get("assignee") or "me")
    url += f"&assignee={quote(assignee)}"
    status, parsed, raw = _call("GET", url, {**_ua(), "Authorization": f"Bearer {token}"}, None, timeout_of(step))
    if status != 200:
        return error_from_http(status, parsed, raw, what="asana")
    data = parsed.get("data") if isinstance(parsed.get("data"), list) else []
    tasks = [{"gid": i.get("gid"), "name": i.get("name")} for i in data if isinstance(i, dict)]
    return {"ok": True, "provider": "asana", "tasks": tasks, "count": len(tasks)}


def telegram(step: Dict[str, Any]) -> Dict[str, Any]:
    token = env_key("TELEGRAM_BOT_TOKEN", "EXO_TELEGRAM_BOT_TOKEN")
    if not token:
        return _auth("telegram", "TELEGRAM_BOT_TOKEN")
    chat = str(step.get("chat_id") or step.get("chat") or step.get("to") or "").strip()
    text = str(step.get("text") or step.get("message") or "").strip()
    if not chat or not text:
        return {"ok": False, "error": "telegram requires chat_id and text", "code": "MISSING_FIELDS"}
    if not parse_confirm(step.get("confirm", False)):
        return {"ok": False, "error": "telegram send requires confirm=true", "code": "CONFIRM_REQUIRED"}
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    status, parsed, raw = _call("POST", url, _ua(), {"chat_id": chat, "text": text}, timeout_of(step))
    if status != 200:
        return error_from_http(status, parsed, raw, what="telegram")
    if parsed.get("ok") is False:
        return {"ok": False, "error": str(parsed.get("description") or "telegram failed"), "code": "TELEGRAM_ERROR"}
    result = parsed.get("result") if isinstance(parsed.get("result"), dict) else {}
    return {"ok": True, "provider": "telegram", "message_id": result.get("message_id")}


def serper(step: Dict[str, Any]) -> Dict[str, Any]:
    key = env_key("SERPER_API_KEY", "EXO_SERPER_API_KEY")
    if not key:
        return _auth("serper", "SERPER_API_KEY")
    query = str(step.get("query") or step.get("q") or "").strip()
    if not query:
        return {"ok": False, "error": "serper requires query", "code": "MISSING_QUERY"}
    status, parsed, raw = _call(
        "POST", "https://google.serper.dev/search",
        {**_ua(), "X-API-KEY": key},
        {"q": query, "num": clip_int(step.get("max") or 5, 5, 1, 15)},
        timeout_of(step),
    )
    if status != 200:
        return error_from_http(status, parsed, raw, what="serper")
    rows = []
    for item in parsed.get("organic") or []:
        if isinstance(item, dict):
            rows.append({"title": item.get("title"), "url": item.get("link")})
    return {"ok": True, "provider": "serper", "results": rows, "count": len(rows)}


def brave(step: Dict[str, Any]) -> Dict[str, Any]:
    key = env_key("BRAVE_API_KEY", "EXO_BRAVE_API_KEY")
    if not key:
        return _auth("brave", "BRAVE_API_KEY")
    query = str(step.get("query") or step.get("q") or "").strip()
    if not query:
        return {"ok": False, "error": "brave requires query", "code": "MISSING_QUERY"}
    url = "https://api.search.brave.com/res/v1/web/search?" + urlencode({
        "q": query, "count": clip_int(step.get("max") or 5, 5, 1, 15),
    })
    status, parsed, raw = _call("GET", url, {**_ua(), "X-Subscription-Token": key}, None, timeout_of(step))
    if status != 200:
        return error_from_http(status, parsed, raw, what="brave")
    web = parsed.get("web") if isinstance(parsed.get("web"), dict) else {}
    rows = []
    for item in web.get("results") or []:
        if isinstance(item, dict):
            rows.append({"title": item.get("title"), "url": item.get("url")})
    return {"ok": True, "provider": "brave", "results": rows, "count": len(rows)}
