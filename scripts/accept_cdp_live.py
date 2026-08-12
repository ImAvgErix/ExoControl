#!/usr/bin/env python3
"""Live CDP / Exo Launcher acceptance (CI-friendly).

Exit codes:
  0  — all required checks passed OR intentionally skipped (no CDP)
  1  — hard failure when CDP was present / required
  2  — usage / import failure

Env:
  EXO_ACCEPT_REQUIRE_CDP=1  — fail (exit 1) if no CDP endpoint is found
  EXO_ACCEPT_CDP_PORT=9222  — optional port hint
"""
from __future__ import annotations

import json
import os
import sys
from typing import Any, Dict, List


def _emit(obj: Dict[str, Any]) -> None:
    print(json.dumps(obj, indent=2, default=str))


def main() -> int:
    try:
        from exo_control import ExoExecEngine
        from aether import exo_bridge
    except Exception as exc:
        _emit({"ok": False, "error": f"import failed: {exc}"})
        return 2

    require = (os.environ.get("EXO_ACCEPT_REQUIRE_CDP") or "").strip() in {"1", "true", "yes"}
    port_raw = (os.environ.get("EXO_ACCEPT_CDP_PORT") or "").strip()
    extra_ports = [int(port_raw)] if port_raw.isdigit() else None

    report: Dict[str, Any] = {
        "ok": True,
        "suite": "accept_cdp_live",
        "require_cdp": require,
        "checks": [],
    }

    def check(name: str, ok: bool, **extra: Any) -> None:
        report["checks"].append({"name": name, "ok": ok, **extra})
        if not ok:
            report["ok"] = False

    endpoints = exo_bridge.discover_cdp_endpoints(extra_ports=extra_ports)
    check(
        "cdp_discover",
        True,  # discover itself always "runs"
        count=len(endpoints or []),
        endpoints=[
            {
                "endpoint": e.get("endpoint"),
                "port": e.get("port"),
                "browser": e.get("browser"),
                "targets": len(e.get("targets") or []),
            }
            for e in (endpoints or [])[:5]
        ],
    )

    if not endpoints:
        check(
            "cdp_present",
            not require,
            skipped=not require,
            reason="no CDP endpoint (start Chrome/Edge/Exo with remote debugging)",
        )
        _emit(report)
        # Skip is success unless required
        return 0 if not require else 1

    eng = ExoExecEngine()
    ep = endpoints[0].get("endpoint") or f"http://127.0.0.1:{endpoints[0].get('port')}"
    script: List[Dict[str, Any]] = [
        {"op": "lease_force_release"},
        {"op": "lease_acquire", "agent_id": "accept-cdp", "task": "cdp-live", "ttl_sec": 90},
        {"op": "browser_connect", "endpoint": ep},
        {"op": "browser_snapshot"},
        {"op": "lease_release"},
    ]
    out = eng.execute(script, stop_on_failure=True)
    steps = {s.get("op"): s for s in out.get("steps") or []}

    conn = (steps.get("browser_connect") or {}).get("result") or {}
    check("browser_connect", bool(conn.get("ok")), result={k: conn.get(k) for k in ("ok", "error", "endpoint", "pages") if k in conn or k == "ok"})

    snap = (steps.get("browser_snapshot") or {}).get("result") or {}
    refs = snap.get("refs") or snap.get("elements") or snap.get("nodes") or []
    textish = snap.get("text") or snap.get("title") or ""
    has_structure = bool(refs) or bool(textish) or bool(snap.get("ok"))
    check(
        "browser_snapshot",
        bool(snap.get("ok")) and has_structure,
        refs=len(refs) if isinstance(refs, list) else 0,
        title=snap.get("title") or snap.get("url"),
        error=snap.get("error"),
    )

    # Honest miss is still ok for connect if CDP died mid-flight
    report["execute_ok"] = out.get("ok")
    report["elapsed_ms"] = out.get("elapsed_ms")
    _emit(report)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
