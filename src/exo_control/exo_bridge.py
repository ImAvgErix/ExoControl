"""
Exo / WebView2 CDP attach helpers.

Finds a live Chromium DevTools endpoint (Chrome, Edge, WebView2 with
remote debugging) and returns a Playwright-compatible CDP URL.

Exo Launcher / ExoOS: launch with EXOOS_CDP=1 (port 9229) when available.
Also probes common ports and reads DevToolsActivePort from WebView2 user-data.
"""
from __future__ import annotations

import json
import os
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional


DEFAULT_PORTS = (9229, 9222, 9333, 9223, 9224, 9230)


def _probe_json(url: str, timeout: float = 0.6) -> Optional[Any]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8", errors="replace"))
    except Exception:
        return None


def discover_cdp_endpoints(extra_ports: Optional[List[int]] = None) -> List[Dict[str, Any]]:
    ports = list(DEFAULT_PORTS)
    if extra_ports:
        ports = list(extra_ports) + ports
    # env override
    for key in ("EXOOS_CDP_PORT", "AETHER_CDP_PORT", "WEBVIEW2_CDP_PORT"):
        val = (os.environ.get(key) or "").strip()
        if val.isdigit():
            ports.insert(0, int(val))
    seen = set()
    found: List[Dict[str, Any]] = []
    for port in ports:
        if port in seen:
            continue
        seen.add(port)
        base = f"http://127.0.0.1:{port}"
        ver = _probe_json(f"{base}/json/version")
        if not isinstance(ver, dict):
            continue
        pages = _probe_json(f"{base}/json/list") or _probe_json(f"{base}/json")
        targets = pages if isinstance(pages, list) else []
        found.append({
            "endpoint": base,
            "port": port,
            "browser": ver.get("Browser") or ver.get("webSocketDebuggerUrl") or "",
            "ws": ver.get("webSocketDebuggerUrl"),
            "targets": [
                {
                    "id": t.get("id"),
                    "title": t.get("title"),
                    "url": t.get("url"),
                    "type": t.get("type"),
                    "webSocketDebuggerUrl": t.get("webSocketDebuggerUrl"),
                }
                for t in targets if isinstance(t, dict)
            ][:20],
        })
    # WebView2 DevToolsActivePort under LocalAppData
    try:
        local = Path(os.environ.get("LOCALAPPDATA", ""))
        candidates = [
            local / "ExoLauncher" / "EBWebView" / "DevToolsActivePort",
            local / "ExoLauncher" / "webview" / "EBWebView" / "DevToolsActivePort",
            local / "ExoOS" / "EBWebView" / "DevToolsActivePort",
        ]
        for p in candidates:
            if not p.is_file():
                continue
            lines = p.read_text(encoding="utf-8", errors="replace").strip().splitlines()
            if not lines:
                continue
            port = int(lines[0].strip())
            if port in seen:
                continue
            base = f"http://127.0.0.1:{port}"
            ver = _probe_json(f"{base}/json/version")
            if isinstance(ver, dict):
                found.append({
                    "endpoint": base,
                    "port": port,
                    "browser": ver.get("Browser") or "WebView2",
                    "ws": ver.get("webSocketDebuggerUrl"),
                    "source": str(p),
                    "targets": [],
                })
    except Exception:
        pass
    return found


def attach_best(browser_engine=None) -> Dict[str, Any]:
    """
    Discover CDP and optionally connect a BrowserEngineSync.
    Returns {ok, endpoint, targets, connected}.
    """
    ends = discover_cdp_endpoints()
    if not ends:
        return {
            "ok": False,
            "error": "No CDP endpoint. Launch Exo/Edge with remote debugging "
                     "(EXOOS_CDP=1 port 9229) or Chrome --remote-debugging-port=9222.",
            "endpoints": [],
        }
    best = ends[0]
    connected = False
    detail = None
    if browser_engine is not None and hasattr(browser_engine, "connect_cdp"):
        try:
            detail = browser_engine.connect_cdp(best["endpoint"])
            connected = bool(detail.get("ok", True)) if isinstance(detail, dict) else True
        except Exception as e:
            detail = {"error": str(e)}
            connected = False
    return {
        "ok": True,
        "endpoint": best["endpoint"],
        "port": best["port"],
        "browser": best.get("browser"),
        "targets": best.get("targets") or [],
        "all": ends,
        "connected": connected,
        "connect_detail": detail,
    }


def read_dom_text(endpoint: str, max_chars: int = 4000) -> Dict[str, Any]:
    """Best-effort: pull document.body.innerText from first page target via CDP HTTP."""
    pages = _probe_json(f"{endpoint.rstrip('/')}/json/list") or _probe_json(f"{endpoint.rstrip('/')}/json")
    if not isinstance(pages, list) or not pages:
        return {"ok": False, "error": "no page targets"}
    # Prefer page type
    page = None
    for t in pages:
        if isinstance(t, dict) and t.get("type") == "page":
            page = t
            break
    page = page or (pages[0] if isinstance(pages[0], dict) else None)
    if not page:
        return {"ok": False, "error": "no page"}
    # Without full CDP client, return metadata; Playwright connect fills DOM.
    title = page.get("title") or ""
    url = page.get("url") or ""
    return {
        "ok": True,
        "title": title,
        "url": url,
        "id": page.get("id"),
        "note": "Use browser_connect_cdp + browser_snapshot for full DOM text.",
        "max_chars": max_chars,
    }
