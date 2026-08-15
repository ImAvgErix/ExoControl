"""Tavily + Exa web search (HTTP, Windows-safe).

Auth: ``TAVILY_API_KEY`` / ``EXA_API_KEY`` (``EXO_*`` aliases).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from exo_control.http_json import clip_int, env_key, error_from_http, request_json, timeout_of, user_agent

_REQUEST_JSON = None
TAVILY_URL = "https://api.tavily.com/search"
EXA_URL = "https://api.exa.ai/search"


def tavily_key() -> Optional[str]:
    return env_key("TAVILY_API_KEY", "EXO_TAVILY_API_KEY")


def exa_key() -> Optional[str]:
    return env_key("EXA_API_KEY", "EXO_EXA_API_KEY")


def tavily_configured() -> bool:
    return bool(tavily_key())


def exa_configured() -> bool:
    return bool(exa_key())


def _call(method: str, url: str, headers: Dict[str, str], payload: Optional[Dict[str, Any]], timeout: float):
    if _REQUEST_JSON is not None:
        return _REQUEST_JSON(method, url, headers, payload, timeout)
    return request_json(method, url, headers, payload, timeout)


def _query(step: Dict[str, Any]) -> str:
    return str(step.get("query") or step.get("q") or step.get("text") or "").strip()


def _rows(parsed: Dict[str, Any]) -> List[Dict[str, Any]]:
    raw = parsed.get("results") or parsed.get("data") or []
    rows = []
    if not isinstance(raw, list):
        return rows
    for item in raw:
        if not isinstance(item, dict):
            continue
        rows.append({
            "title": item.get("title"),
            "url": item.get("url") or item.get("href"),
            "content": item.get("content") or item.get("text") or item.get("snippet"),
        })
    return rows


def tavily(step: Dict[str, Any]) -> Dict[str, Any]:
    key = tavily_key()
    if not key:
        return {
            "ok": False,
            "error": "tavily requires TAVILY_API_KEY",
            "code": "AUTHENTICATION",
            "hint": "export TAVILY_API_KEY",
        }
    query = _query(step)
    if not query:
        return {"ok": False, "error": "tavily requires query", "code": "MISSING_QUERY"}
    top = clip_int(step.get("max") or step.get("limit") or 5, 5, 1, 15)
    status, parsed, raw = _call(
        "POST",
        TAVILY_URL,
        {"Content-Type": "application/json", "Accept": "application/json", "User-Agent": user_agent()},
        {"api_key": key, "query": query, "max_results": top},
        timeout_of(step),
    )
    if status not in {200, 201}:
        return error_from_http(status, parsed, raw, what="tavily")
    results = _rows(parsed)
    return {"ok": True, "provider": "tavily", "query": query, "results": results, "count": len(results)}


def exa(step: Dict[str, Any]) -> Dict[str, Any]:
    key = exa_key()
    if not key:
        return {
            "ok": False,
            "error": "exa requires EXA_API_KEY",
            "code": "AUTHENTICATION",
            "hint": "export EXA_API_KEY",
        }
    query = _query(step)
    if not query:
        return {"ok": False, "error": "exa requires query", "code": "MISSING_QUERY"}
    top = clip_int(step.get("max") or step.get("limit") or 5, 5, 1, 15)
    status, parsed, raw = _call(
        "POST",
        EXA_URL,
        {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": user_agent(),
        },
        {"query": query, "numResults": top},
        timeout_of(step),
    )
    if status not in {200, 201}:
        return error_from_http(status, parsed, raw, what="exa")
    results = _rows(parsed)
    return {"ok": True, "provider": "exa", "query": query, "results": results, "count": len(results)}
