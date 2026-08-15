"""Perplexity Search as Code — lease-free web retrieval for any harness.

The compiled ``pplx-srch-sdk`` package is Linux/macOS + CPython 3.12 only and
does not run on Windows (Exo Control's target). These ops use the official
Search API HTTP contract instead, so agents get the same primitives: fan-out
queries, then filter / dedupe / rank in the result payload.

Auth: ``PERPLEXITY_API_KEY`` (alias ``EXO_PERPLEXITY_API_KEY``).
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
from urllib.parse import urlparse


SEARCH_URL = "https://api.perplexity.ai/search"
MAX_QUERIES = 5
MAX_RESULTS = 20
DEFAULT_RESULTS = 5
DEFAULT_SNIPPET_CHARS = 320
VERBOSE_SNIPPET_CHARS = 1200
DEFAULT_TIMEOUT = 30.0
MAX_TIMEOUT = 60.0

# Tests replace this.
_POST_JSON = None


def api_key() -> Optional[str]:
    for name in ("PERPLEXITY_API_KEY", "EXO_PERPLEXITY_API_KEY"):
        raw = (os.environ.get(name) or "").strip()
        if raw:
            return raw
    return None


def configured() -> bool:
    return bool(api_key())


def _auth_denied() -> Dict[str, Any]:
    return {
        "ok": False,
        "error": "search requires PERPLEXITY_API_KEY",
        "code": "AUTHENTICATION",
        "hint": "export PERPLEXITY_API_KEY from https://www.perplexity.ai/account/api",
    }


def _clip_int(value: Any, default: int, lo: int, hi: int) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, n))


def _as_queries(step: Dict[str, Any]) -> List[str]:
    raw = step.get("query")
    if raw is None:
        raw = step.get("q")
    if raw is None:
        raw = step.get("queries")
    if raw is None:
        raw = step.get("text")
    if raw is None:
        return []
    if isinstance(raw, str):
        q = raw.strip()
        return [q] if q else []
    if isinstance(raw, Sequence) and not isinstance(raw, (bytes, bytearray)):
        out: List[str] = []
        for item in raw:
            s = str(item or "").strip()
            if s:
                out.append(s)
        return out
    s = str(raw).strip()
    return [s] if s else []


def _as_str_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        s = value.strip()
        return [s] if s else []
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        out: List[str] = []
        for item in value:
            s = str(item or "").strip()
            if s:
                out.append(s)
        return out
    s = str(value).strip()
    return [s] if s else []


def _domain_from_url(url: str) -> str:
    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        return ""
    if host.startswith("www."):
        host = host[4:]
    return host


def _norm_url(url: str) -> str:
    raw = (url or "").strip()
    if not raw:
        return ""
    try:
        parts = urlparse(raw)
        host = (parts.hostname or "").lower()
        if host.startswith("www."):
            host = host[4:]
        path = parts.path or ""
        if path != "/" and path.endswith("/"):
            path = path[:-1]
        query = f"?{parts.query}" if parts.query else ""
        return f"{host}{path}{query}"
    except Exception:
        return raw.rstrip("/").lower()


def _truncate(text: str, limit: int) -> str:
    if limit <= 0:
        return ""
    if len(text) <= limit:
        return text
    if limit <= 3:
        return text[:limit]
    return text[: limit - 3] + "..."


def _chunks(items: Sequence[str], size: int) -> Iterable[List[str]]:
    for i in range(0, len(items), size):
        yield list(items[i : i + size])


def _http_post_json(url: str, headers: Dict[str, str], payload: Dict[str, Any], timeout: float) -> Tuple[int, Dict[str, Any], str]:
    if _POST_JSON is not None:
        return _POST_JSON(url, headers, payload, timeout)
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
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
    err = parsed.get("error") if isinstance(parsed.get("error"), dict) else {}
    code = str(err.get("code") or "")
    message = str(err.get("message") or parsed.get("message") or "").strip()
    if not code:
        if status in {401, 403}:
            code = "AUTHENTICATION" if status == 401 else "FORBIDDEN"
        elif status == 429:
            code = "RATE_LIMIT"
        elif status == 400:
            code = "BAD_REQUEST"
        elif status == 404:
            code = "NOT_FOUND"
        elif status >= 500:
            code = "INTERNAL_SERVER"
        elif status == 0:
            code = str((parsed.get("error") or {}).get("code") or "CONNECT")
        else:
            code = "UNKNOWN"
    if not message:
        message = raw[:240] if raw else f"search HTTP {status}"
    return {
        "ok": False,
        "error": message,
        "code": code,
        "http_status": status or None,
    }


def _hit_from_raw(item: Any, snippet_limit: int, query: Optional[str] = None) -> Optional[Dict[str, Any]]:
    if not isinstance(item, dict):
        return None
    url = str(item.get("url") or item.get("link") or "").strip()
    title = str(item.get("title") or "").strip()
    snippet = str(item.get("snippet") or item.get("text") or item.get("summary") or "")
    if not url and not title and not snippet:
        return None
    domain = str(item.get("domain") or _domain_from_url(url))
    hit: Dict[str, Any] = {
        "title": title,
        "url": url,
        "domain": domain,
        "snippet": _truncate(snippet, snippet_limit),
    }
    if query:
        hit["query"] = query
    date = item.get("date") or item.get("published")
    if date:
        hit["date"] = date
    updated = item.get("last_updated") or item.get("updated")
    if updated:
        hit["last_updated"] = updated
    return hit


def _flatten_results(parsed: Dict[str, Any], queries: Sequence[str], snippet_limit: int) -> List[Dict[str, Any]]:
    raw = parsed.get("results")
    hits: List[Dict[str, Any]] = []
    if isinstance(raw, list) and raw and all(isinstance(x, list) for x in raw):
        for idx, group in enumerate(raw):
            q = queries[idx] if idx < len(queries) else None
            for item in group:
                hit = _hit_from_raw(item, snippet_limit, query=q)
                if hit:
                    hits.append(hit)
        return hits
    if isinstance(raw, list):
        q = queries[0] if len(queries) == 1 else None
        for item in raw:
            hit = _hit_from_raw(item, snippet_limit, query=q)
            if hit:
                hits.append(hit)
        return hits
    return hits


def _dedupe(hits: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    out: List[Dict[str, Any]] = []
    for hit in hits:
        key = _norm_url(str(hit.get("url") or "")) or (
            str(hit.get("title") or "").lower(),
            str(hit.get("domain") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(hit)
    return out


def _filter_contains(hits: List[Dict[str, Any]], needles: Sequence[str]) -> List[Dict[str, Any]]:
    if not needles:
        return hits
    lowered = [n.lower() for n in needles if n]
    if not lowered:
        return hits
    out: List[Dict[str, Any]] = []
    for hit in hits:
        blob = " ".join(
            str(hit.get(k) or "") for k in ("title", "snippet", "url", "domain", "query")
        ).lower()
        if any(n in blob for n in lowered):
            out.append(hit)
    return out


def _rank(hits: List[Dict[str, Any]], mode: str) -> List[Dict[str, Any]]:
    mode = (mode or "api").strip().lower()
    if mode in {"recency", "date", "newest"}:
        def key(hit: Dict[str, Any]) -> str:
            return str(hit.get("last_updated") or hit.get("date") or "")
        return sorted(hits, key=key, reverse=True)
    return hits


def _domain_filter(step: Dict[str, Any], extra: Optional[Sequence[str]] = None) -> List[str]:
    allow = _as_str_list(step.get("domains") or step.get("search_domain_filter") or step.get("allow"))
    deny = _as_str_list(step.get("exclude_domains") or step.get("deny"))
    out = list(allow)
    for host in extra or []:
        if host and host not in out:
            out.append(host)
    for host in deny:
        token = host if host.startswith("-") else f"-{host}"
        if token not in out:
            out.append(token)
    return out[:20]


def _search_payload(step: Dict[str, Any], queries: Sequence[str], *, extra_domains: Optional[Sequence[str]] = None) -> Dict[str, Any]:
    verbose = step.get("verbose") is True
    max_results = _clip_int(
        step.get("max") or step.get("limit") or step.get("max_results"),
        DEFAULT_RESULTS if not verbose else 10,
        1,
        MAX_RESULTS,
    )
    payload: Dict[str, Any] = {
        "query": list(queries) if len(queries) > 1 else queries[0],
        "max_results": max_results,
    }
    country = step.get("country")
    if country:
        payload["country"] = str(country).strip().upper()
    languages = _as_str_list(step.get("languages") or step.get("search_language_filter") or step.get("language"))
    if languages:
        payload["search_language_filter"] = languages[:10]
    domains = _domain_filter(step, extra_domains)
    if domains:
        payload["search_domain_filter"] = domains
    recency = step.get("recency") or step.get("search_recency_filter") or step.get("recency_filter")
    if recency:
        payload["search_recency_filter"] = str(recency).strip().lower()
    context = step.get("search_context_size") or step.get("context")
    max_tokens = step.get("max_tokens")
    max_tokens_per_page = step.get("max_tokens_per_page")
    if max_tokens is not None or max_tokens_per_page is not None:
        if max_tokens is not None:
            payload["max_tokens"] = _clip_int(max_tokens, 5000, 1, 1_000_000)
        if max_tokens_per_page is not None:
            payload["max_tokens_per_page"] = _clip_int(max_tokens_per_page, 1024, 1, 50_000)
    elif context:
        payload["search_context_size"] = str(context).strip().lower()
    elif not verbose:
        payload["search_context_size"] = "low"
    return payload


def _headers(key: str) -> Dict[str, str]:
    from exo_control import __version__

    return {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": f"exo-control/{__version__}",
    }


def _run_search(step: Dict[str, Any], queries: List[str], *, extra_domains: Optional[Sequence[str]] = None) -> Dict[str, Any]:
    key = api_key()
    if not key:
        return _auth_denied()
    if not queries:
        return {"ok": False, "error": "search requires query", "code": "MISSING_QUERY"}

    verbose = step.get("verbose") is True
    snippet_limit = _clip_int(
        step.get("snippet_chars") or step.get("snippet_limit"),
        VERBOSE_SNIPPET_CHARS if verbose else DEFAULT_SNIPPET_CHARS,
        40,
        8000,
    )
    timeout = min(MAX_TIMEOUT, max(2.0, float(step.get("timeout", DEFAULT_TIMEOUT))))
    headers = _headers(key)
    hits: List[Dict[str, Any]] = []
    search_id = None
    batches = 0
    for batch in _chunks(queries, MAX_QUERIES):
        batches += 1
        payload = _search_payload(step, batch, extra_domains=extra_domains)
        status, parsed, raw = _http_post_json(SEARCH_URL, headers, payload, timeout)
        if status != 200:
            return _error_from_http(status, parsed, raw)
        if search_id is None:
            search_id = parsed.get("id")
        hits.extend(_flatten_results(parsed, batch, snippet_limit))

    fetched = len(hits)
    if step.get("dedupe", True) is not False:
        hits = _dedupe(hits)
    contains = _as_str_list(step.get("contains") or step.get("filter"))
    hits = _filter_contains(hits, contains)
    hits = _rank(hits, str(step.get("rank") or "api"))

    max_keep = _clip_int(step.get("keep_max") or len(hits) or 1, len(hits) or 1, 1, 80)
    if not verbose and "keep_max" not in step:
        max_keep = min(max_keep, 12)
    trimmed = hits[:max_keep]
    return {
        "ok": True,
        "provider": "perplexity",
        "id": search_id,
        "queries": list(queries),
        "count": len(trimmed),
        "total": fetched,
        "dropped": max(0, fetched - len(trimmed)),
        "results": trimmed,
        "batches": batches,
    }


def search_web(step: Dict[str, Any]) -> Dict[str, Any]:
    """Fan-out web search. ``query`` may be a string or a list (max 5 per request)."""
    return _run_search(step, _as_queries(step))


def search_content(step: Dict[str, Any]) -> Dict[str, Any]:
    """Query-relevant snippets scoped to ``urls`` (Search API domain filter)."""
    urls = _as_str_list(step.get("urls") or step.get("url") or step.get("pages"))
    if not urls:
        return {"ok": False, "error": "search_content requires urls", "code": "MISSING_URLS"}
    queries = _as_queries(step)
    if not queries:
        host = _domain_from_url(urls[0]) or urls[0]
        queries = [f"key facts from {host}"]
    domains = [_domain_from_url(u) for u in urls]
    domains = [d for d in domains if d]
    out = _run_search(step, queries, extra_domains=domains)
    if not out.get("ok"):
        return out
    wanted = {_norm_url(u) for u in urls}
    wanted_hosts = {_domain_from_url(u) for u in urls if _domain_from_url(u)}
    scoped: List[Dict[str, Any]] = []
    for hit in out.get("results") or []:
        url = str(hit.get("url") or "")
        if _norm_url(url) in wanted or _domain_from_url(url) in wanted_hosts:
            scoped.append(hit)
    if scoped:
        out["results"] = scoped
        out["count"] = len(scoped)
    out["urls"] = urls
    out["dropped"] = max(0, int(out.get("total") or 0) - int(out.get("count") or 0))
    return out
