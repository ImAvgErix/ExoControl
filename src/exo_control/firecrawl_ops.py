"""Firecrawl — URL to markdown / site map / crawl (HTTP, Windows-safe).

Auth: ``FIRECRAWL_API_KEY`` (alias ``EXO_FIRECRAWL_API_KEY``).
"""
from __future__ import annotations

import os
from typing import Any, Dict, Optional

from exo_control.http_json import clip_int, env_key, error_from_http, request_json, timeout_of, truncate, user_agent

_REQUEST_JSON = None
DEFAULT_BASE = "https://api.firecrawl.dev/v1"


def api_key() -> Optional[str]:
    return env_key("FIRECRAWL_API_KEY", "EXO_FIRECRAWL_API_KEY")


def configured() -> bool:
    return bool(api_key())


def _auth_denied() -> Dict[str, Any]:
    return {
        "ok": False,
        "error": "scrape requires FIRECRAWL_API_KEY",
        "code": "AUTHENTICATION",
        "hint": "export FIRECRAWL_API_KEY from https://www.firecrawl.dev",
    }


def _base() -> str:
    return (os.environ.get("FIRECRAWL_API_URL") or os.environ.get("EXO_FIRECRAWL_API_URL") or DEFAULT_BASE).rstrip("/")


def _headers(key: str) -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": user_agent(),
    }


def _call(method: str, url: str, headers: Dict[str, str], payload: Optional[Dict[str, Any]], timeout: float):
    if _REQUEST_JSON is not None:
        return _REQUEST_JSON(method, url, headers, payload, timeout)
    return request_json(method, url, headers, payload, timeout)


def _url_of(step: Dict[str, Any]) -> str:
    return str(step.get("url") or step.get("page") or step.get("href") or "").strip()


def scrape(step: Dict[str, Any]) -> Dict[str, Any]:
    key = api_key()
    if not key:
        return _auth_denied()
    url = _url_of(step)
    if not url:
        return {"ok": False, "error": "scrape requires url", "code": "MISSING_URL"}
    payload: Dict[str, Any] = {"url": url, "formats": ["markdown"]}
    status, parsed, raw = _call("POST", f"{_base()}/scrape", _headers(key), payload, timeout_of(step))
    if status not in {200, 201}:
        return error_from_http(status, parsed, raw, what="scrape")
    data = parsed.get("data") if isinstance(parsed.get("data"), dict) else parsed
    markdown = str(data.get("markdown") or data.get("content") or "")
    meta = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
    verbose = step.get("verbose") is True
    limit = 12000 if verbose else 4000
    return {
        "ok": True,
        "provider": "firecrawl",
        "url": url,
        "title": str(meta.get("title") or data.get("title") or ""),
        "markdown": truncate(markdown, limit),
        "chars": len(markdown),
    }


def site_map(step: Dict[str, Any]) -> Dict[str, Any]:
    key = api_key()
    if not key:
        return _auth_denied()
    url = _url_of(step)
    if not url:
        return {"ok": False, "error": "site_map requires url", "code": "MISSING_URL"}
    status, parsed, raw = _call(
        "POST", f"{_base()}/map", _headers(key), {"url": url}, timeout_of(step)
    )
    if status not in {200, 201}:
        return error_from_http(status, parsed, raw, what="site_map")
    links = parsed.get("links") or parsed.get("urls") or []
    if not isinstance(links, list):
        links = []
    keep = clip_int(step.get("max") or step.get("limit") or 40, 40, 1, 200)
    trimmed = [str(x) for x in links[:keep]]
    return {"ok": True, "provider": "firecrawl", "url": url, "links": trimmed, "count": len(trimmed), "total": len(links)}


def crawl(step: Dict[str, Any]) -> Dict[str, Any]:
    key = api_key()
    if not key:
        return _auth_denied()
    job_id = str(step.get("id") or step.get("job_id") or step.get("run_id") or "").strip()
    headers = _headers(key)
    timeout = timeout_of(step)
    if job_id:
        status, parsed, raw = _call("GET", f"{_base()}/crawl/{job_id}", headers, None, timeout)
        if status != 200:
            return error_from_http(status, parsed, raw, what="crawl")
        parsed["ok"] = True
        parsed["provider"] = "firecrawl"
        parsed["id"] = parsed.get("id") or job_id
        return parsed
    url = _url_of(step)
    if not url:
        return {"ok": False, "error": "crawl requires url or id", "code": "MISSING_URL"}
    payload: Dict[str, Any] = {"url": url}
    limit = step.get("limit") or step.get("max")
    if limit is not None:
        payload["limit"] = clip_int(limit, 10, 1, 100)
    status, parsed, raw = _call("POST", f"{_base()}/crawl", headers, payload, timeout)
    if status not in {200, 201}:
        return error_from_http(status, parsed, raw, what="crawl")
    return {
        "ok": True,
        "provider": "firecrawl",
        "id": parsed.get("id") or parsed.get("jobId"),
        "status": parsed.get("status") or "started",
        "url": url,
    }
