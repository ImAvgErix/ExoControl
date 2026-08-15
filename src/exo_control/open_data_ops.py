"""Key-free open data: DDG, Wikipedia, weather, RSS, HN, arXiv."""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional
from urllib.parse import quote, urlencode

from exo_control.http_json import clip_int, error_from_http, request_json, request_text, timeout_of, user_agent

_REQUEST_JSON = None
_REQUEST_TEXT = None


def configured() -> bool:
    return True


def _headers() -> Dict[str, str]:
    return {"Accept": "application/json, text/xml, */*", "User-Agent": user_agent()}


def _call(method: str, url: str, headers: Dict[str, str], payload: Optional[Dict[str, Any]], timeout: float):
    if _REQUEST_JSON is not None:
        return _REQUEST_JSON(method, url, headers, payload, timeout)
    return request_json(method, url, headers, payload, timeout)


def _call_text(method: str, url: str, headers: Dict[str, str], timeout: float):
    if _REQUEST_TEXT is not None:
        return _REQUEST_TEXT(method, url, headers, timeout)
    return request_text(method, url, headers, timeout)


def _query(step: Dict[str, Any]) -> str:
    return str(step.get("query") or step.get("q") or step.get("text") or "").strip()


def ddg(step: Dict[str, Any]) -> Dict[str, Any]:
    query = _query(step)
    if not query:
        return {"ok": False, "error": "ddg requires query", "code": "MISSING_QUERY"}
    url = "https://api.duckduckgo.com/?" + urlencode({"q": query, "format": "json", "no_html": 1})
    status, parsed, raw = _call("GET", url, _headers(), None, timeout_of(step))
    if status != 200:
        return error_from_http(status, parsed, raw, what="ddg")
    topics = []
    for item in parsed.get("RelatedTopics") or []:
        if isinstance(item, dict) and item.get("Text"):
            topics.append({"text": item.get("Text"), "url": item.get("FirstURL")})
    return {
        "ok": True,
        "provider": "duckduckgo",
        "abstract": parsed.get("AbstractText") or parsed.get("Abstract") or "",
        "topics": topics[: clip_int(step.get("max") or 8, 8, 1, 20)],
    }


def wiki(step: Dict[str, Any]) -> Dict[str, Any]:
    query = _query(step)
    if not query:
        return {"ok": False, "error": "wiki requires query", "code": "MISSING_QUERY"}
    url = "https://en.wikipedia.org/w/api.php?" + urlencode({
        "action": "opensearch", "search": query, "limit": clip_int(step.get("max") or 5, 5, 1, 15),
        "namespace": 0, "format": "json",
    })
    status, parsed, raw = _call("GET", url, _headers(), None, timeout_of(step))
    if status != 200:
        return error_from_http(status, parsed, raw, what="wiki")
    arr = parsed.get("value") if isinstance(parsed.get("value"), list) else parsed
    titles: List[str] = []
    descs: List[str] = []
    urls: List[str] = []
    if isinstance(arr, list) and len(arr) >= 4:
        titles = [str(x) for x in (arr[1] or [])]
        descs = [str(x) for x in (arr[2] or [])]
        urls = [str(x) for x in (arr[3] or [])]
    results = []
    for i, title in enumerate(titles):
        results.append({
            "title": title,
            "summary": descs[i] if i < len(descs) else "",
            "url": urls[i] if i < len(urls) else "",
        })
    return {"ok": True, "provider": "wikipedia", "results": results, "count": len(results)}


def weather(step: Dict[str, Any]) -> Dict[str, Any]:
    city = str(step.get("city") or step.get("q") or step.get("query") or "").strip()
    lat = step.get("lat") or step.get("latitude")
    lon = step.get("lon") or step.get("longitude")
    if city and (lat is None or lon is None):
        geo = "https://geocoding-api.open-meteo.com/v1/search?" + urlencode({"name": city, "count": 1})
        status, parsed, raw = _call("GET", geo, _headers(), None, timeout_of(step))
        if status != 200:
            return error_from_http(status, parsed, raw, what="weather")
        hits = parsed.get("results") or []
        if not hits or not isinstance(hits[0], dict):
            return {"ok": False, "error": f"city not found: {city}", "code": "NOT_FOUND"}
        lat = hits[0].get("latitude")
        lon = hits[0].get("longitude")
        city = str(hits[0].get("name") or city)
    if lat is None or lon is None:
        return {"ok": False, "error": "weather requires city or lat/lon", "code": "MISSING_LOCATION"}
    url = "https://api.open-meteo.com/v1/forecast?" + urlencode({
        "latitude": lat, "longitude": lon, "current": "temperature_2m,weather_code",
    })
    status, parsed, raw = _call("GET", url, _headers(), None, timeout_of(step))
    if status != 200:
        return error_from_http(status, parsed, raw, what="weather")
    current = parsed.get("current") if isinstance(parsed.get("current"), dict) else {}
    return {
        "ok": True,
        "provider": "open-meteo",
        "city": city or None,
        "lat": lat,
        "lon": lon,
        "temperature": current.get("temperature_2m"),
        "current": current,
    }


def rss(step: Dict[str, Any]) -> Dict[str, Any]:
    url = str(step.get("url") or step.get("feed") or step.get("href") or "").strip()
    if not url:
        return {"ok": False, "error": "rss requires url", "code": "MISSING_URL"}
    status, text, raw = _call_text("GET", url, _headers(), timeout_of(step))
    if status != 200:
        return error_from_http(status, {"error": text}, raw or text, what="rss")
    titles = re.findall(r"<title>(.*?)</title>", text, flags=re.I | re.S)
    items = [{"title": re.sub(r"<[^>]+>", "", t).strip()} for t in titles[1: clip_int(step.get("max") or 8, 8, 1, 20) + 1]]
    if not items and titles:
        items = [{"title": re.sub(r"<[^>]+>", "", titles[0]).strip()}]
    return {"ok": True, "provider": "rss", "url": url, "items": items, "count": len(items)}


def hn(step: Dict[str, Any]) -> Dict[str, Any]:
    query = _query(step)
    params = {"query": query or "front", "hitsPerPage": clip_int(step.get("max") or 8, 8, 1, 20)}
    url = "https://hn.algolia.com/api/v1/search?" + urlencode(params)
    status, parsed, raw = _call("GET", url, _headers(), None, timeout_of(step))
    if status != 200:
        return error_from_http(status, parsed, raw, what="hn")
    hits = []
    for item in parsed.get("hits") or []:
        if isinstance(item, dict):
            hits.append({"title": item.get("title") or item.get("story_title"), "url": item.get("url")})
    return {"ok": True, "provider": "hn", "hits": hits, "count": len(hits)}


def arxiv(step: Dict[str, Any]) -> Dict[str, Any]:
    query = _query(step)
    if not query:
        return {"ok": False, "error": "arxiv requires query", "code": "MISSING_QUERY"}
    url = "https://export.arxiv.org/api/query?" + urlencode({
        "search_query": f"all:{query}", "start": 0, "max_results": clip_int(step.get("max") or 5, 5, 1, 15),
    })
    status, text, raw = _call_text("GET", url, _headers(), timeout_of(step))
    if status != 200:
        return error_from_http(status, {"error": text}, raw or text, what="arxiv")
    titles = [re.sub(r"\s+", " ", t).strip() for t in re.findall(r"<title>(.*?)</title>", text, flags=re.I | re.S)]
    papers = [{"title": t} for t in titles[1:6]]
    return {"ok": True, "provider": "arxiv", "papers": papers, "count": len(papers)}
