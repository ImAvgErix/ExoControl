"""Slack / Notion / Linear — lease-free HTTP. Posts need confirm=true."""
from __future__ import annotations

from typing import Any, Dict, Optional

from exo_control.http_json import clip_int, env_key, error_from_http, request_json, timeout_of, user_agent
from exo_control.policy import parse_confirm

_REQUEST_JSON = None
SLACK_API = "https://slack.com/api"
NOTION_API = "https://api.notion.com/v1"
LINEAR_API = "https://api.linear.app/graphql"


def slack_token() -> Optional[str]:
    return env_key("SLACK_BOT_TOKEN", "SLACK_TOKEN", "EXO_SLACK_TOKEN")


def notion_key() -> Optional[str]:
    return env_key("NOTION_API_KEY", "NOTION_TOKEN", "EXO_NOTION_API_KEY")


def linear_key() -> Optional[str]:
    return env_key("LINEAR_API_KEY", "EXO_LINEAR_API_KEY")


def slack_configured() -> bool:
    return bool(slack_token())


def notion_configured() -> bool:
    return bool(notion_key())


def linear_configured() -> bool:
    return bool(linear_key())


def _call(method: str, url: str, headers: Dict[str, str], payload: Optional[Dict[str, Any]], timeout: float):
    if _REQUEST_JSON is not None:
        return _REQUEST_JSON(method, url, headers, payload, timeout)
    return request_json(method, url, headers, payload, timeout)


def _auth(what: str, env: str) -> Dict[str, Any]:
    return {
        "ok": False,
        "error": f"{what} requires {env}",
        "code": "AUTHENTICATION",
        "hint": f"export {env}",
    }


def slack(step: Dict[str, Any]) -> Dict[str, Any]:
    token = slack_token()
    if not token:
        return _auth("slack", "SLACK_BOT_TOKEN")
    text = str(step.get("text") or step.get("message") or step.get("body") or "").strip()
    channel = str(step.get("channel") or step.get("to") or "").strip()
    action = str(step.get("action") or ("post" if text else "list")).lower()
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": user_agent(),
    }
    if action in {"post", "send", "message"} or (text and channel):
        if not parse_confirm(step.get("confirm", False)):
            return {"ok": False, "error": "slack post requires confirm=true", "code": "CONFIRM_REQUIRED"}
        if not channel or not text:
            return {"ok": False, "error": "slack post requires channel and text", "code": "MISSING_FIELDS"}
        status, parsed, raw = _call(
            "POST", f"{SLACK_API}/chat.postMessage", headers,
            {"channel": channel, "text": text}, timeout_of(step),
        )
        if status != 200:
            return error_from_http(status, parsed, raw, what="slack")
        if parsed.get("ok") is False:
            return {"ok": False, "error": str(parsed.get("error") or "slack post failed"), "code": "SLACK_ERROR"}
        return {"ok": True, "provider": "slack", "channel": channel, "ts": parsed.get("ts")}
    top = clip_int(step.get("max") or 20, 20, 1, 100)
    status, parsed, raw = _call(
        "GET", f"{SLACK_API}/conversations.list?limit={top}", headers, None, timeout_of(step),
    )
    if status != 200:
        return error_from_http(status, parsed, raw, what="slack")
    channels = []
    for item in parsed.get("channels") or []:
        if isinstance(item, dict):
            channels.append({"id": item.get("id"), "name": item.get("name")})
    return {"ok": True, "provider": "slack", "channels": channels, "count": len(channels)}


def notion(step: Dict[str, Any]) -> Dict[str, Any]:
    key = notion_key()
    if not key:
        return _auth("notion", "NOTION_API_KEY")
    query = str(step.get("query") or step.get("q") or step.get("text") or "").strip()
    payload: Dict[str, Any] = {"page_size": clip_int(step.get("max") or 8, 8, 1, 25)}
    if query:
        payload["query"] = query
    status, parsed, raw = _call(
        "POST",
        f"{NOTION_API}/search",
        {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Notion-Version": "2022-06-28",
            "User-Agent": user_agent(),
        },
        payload,
        timeout_of(step),
    )
    if status != 200:
        return error_from_http(status, parsed, raw, what="notion")
    pages = []
    for item in parsed.get("results") or []:
        if isinstance(item, dict):
            pages.append({"id": item.get("id"), "object": item.get("object"), "url": item.get("url")})
    return {"ok": True, "provider": "notion", "pages": pages, "count": len(pages)}


def linear(step: Dict[str, Any]) -> Dict[str, Any]:
    key = linear_key()
    if not key:
        return _auth("linear", "LINEAR_API_KEY")
    query = str(step.get("query") or step.get("q") or step.get("text") or "").strip()
    first = clip_int(step.get("max") or 10, 10, 1, 25)
    gql = (
        "query($first: Int!, $q: String) {"
        " issues(first: $first, filter: { title: { containsIgnoreCase: $q } }) {"
        " nodes { id title identifier }"
        " }"
        "}"
    )
    if not query:
        gql = "query($first: Int!) { issues(first: $first) { nodes { id title identifier } } }"
    payload: Dict[str, Any] = {"query": gql, "variables": {"first": first}}
    if query:
        payload["variables"]["q"] = query
    status, parsed, raw = _call(
        "POST",
        LINEAR_API,
        {
            "Authorization": key,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": user_agent(),
        },
        payload,
        timeout_of(step),
    )
    if status != 200:
        return error_from_http(status, parsed, raw, what="linear")
    nodes = ((parsed.get("data") or {}).get("issues") or {}).get("nodes") or []
    issues = []
    for item in nodes:
        if isinstance(item, dict):
            issues.append({
                "id": item.get("id"),
                "title": item.get("title"),
                "identifier": item.get("identifier"),
            })
    return {"ok": True, "provider": "linear", "issues": issues, "count": len(issues)}
