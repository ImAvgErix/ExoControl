#!/usr/bin/env python3
"""Always-on CDP acceptance: launch Chromium with remote debugging, exercise browser ops.

Exit 0 on success, 1 on failure. For CI (Windows/Linux with playwright chromium).
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path


def _log(msg: str) -> None:
    print(f"[accept_cdp] {msg}", flush=True)


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = int(s.getsockname()[1])
    s.close()
    return port


def _find_chromium() -> str:
    """Locate a browser binary without starting Playwright (avoids driver teardown races)."""
    env = (os.environ.get("EXO_CHROMIUM_PATH") or "").strip()
    if env and Path(env).exists():
        return env
    # Playwright cache layouts
    roots = []
    local = os.environ.get("LOCALAPPDATA") or ""
    if local:
        roots.append(Path(local) / "ms-playwright")
    roots.append(Path.home() / ".cache" / "ms-playwright")
    for root in roots:
        if not root.exists():
            continue
        for pattern in (
            "chromium-*/chrome-win64/chrome.exe",
            "chromium-*/chrome-win/chrome.exe",
            "chromium-*/chrome-linux/chrome",
            "chromium-*/chrome-mac/Chromium.app/Contents/MacOS/Chromium",
        ):
            hits = sorted(root.glob(pattern), reverse=True)
            if hits:
                return str(hits[0])
    for cand in (
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        "/usr/bin/google-chrome",
        "/usr/bin/chromium-browser",
        "/usr/bin/chromium",
    ):
        if Path(cand).exists():
            return cand
    raise SystemExit("No Chromium/Chrome/Edge found; install playwright chromium or set EXO_CHROMIUM_PATH")


def main() -> int:
    port = int(os.environ.get("EXO_ACCEPT_CDP_PORT") or _free_port())
    user_data = Path(os.environ.get("TEMP") or "/tmp") / f"exo-cdp-{port}"
    user_data.mkdir(parents=True, exist_ok=True)
    chrome = _find_chromium()
    _log(f"chromium={chrome} port={port}")
    url = "https://example.com/"
    # Start on about:blank so the browser is up before navigate (more reliable CDP attach).
    args = [
        chrome,
        f"--remote-debugging-port={port}",
        "--remote-debugging-address=127.0.0.1",
        "--remote-allow-origins=*",
        f"--user-data-dir={user_data}",
        "--headless=new",
        "--disable-gpu",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-dev-shm-usage",
        "about:blank",
    ]
    creation = int(getattr(subprocess, "CREATE_NO_WINDOW", 0))
    proc = subprocess.Popen(
        args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=creation
    )
    endpoint = f"http://127.0.0.1:{port}"
    try:
        deadline = time.time() + 25
        ready = False
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(endpoint + "/json/version", timeout=1.5) as resp:
                    if resp.status == 200:
                        ready = True
                        break
            except Exception:
                time.sleep(0.3)
        if not ready:
            print(json.dumps({"ok": False, "error": "CDP not ready", "endpoint": endpoint}))
            return 1
        _log("CDP ready")

        from exo_control import ExoExecEngine

        eng = ExoExecEngine()
        _log("connecting via ExoExecEngine")
        out = eng.execute(
            [
                {"op": "lease_force_release"},
                {"op": "lease_acquire", "agent_id": "ci-cdp", "task": "chromium", "ttl_sec": 90},
                {"op": "browser_connect", "endpoint": endpoint},
                {"op": "browser_navigate", "url": url},
                {"op": "browser_snapshot"},
                {"op": "lease_release"},
            ],
            stop_on_failure=True,
            screenshot_on_fail=False,
        )
        _log(f"execute done ok={out.get('ok')} ms={out.get('elapsed_ms')}")
        snap = next((s for s in out["steps"] if s["op"] == "browser_snapshot"), None)
        snap_r = (snap or {}).get("result") or {}
        text = (snap_r.get("text_sample") or snap_r.get("title") or "") or ""
        has_example = "example" in text.lower() or int(snap_r.get("element_count") or 0) > 0
        report = {
            "ok": bool(out.get("ok")) and bool(snap_r.get("ok")) and has_example,
            "endpoint": endpoint,
            "elapsed_ms": out.get("elapsed_ms"),
            "snapshot_ok": bool(snap_r.get("ok")),
            "element_count": snap_r.get("element_count"),
            "title": snap_r.get("title"),
            "steps": [
                {"op": s["op"], "ok": s["ok"], "error": (s.get("result") or {}).get("error")}
                for s in out.get("steps") or []
            ],
        }
        print(json.dumps(report, indent=2, default=str))
        return 0 if report["ok"] else 1
    finally:
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass


if __name__ == "__main__":
    sys.exit(main())
