"""Drive Aether from a shell without the MCP transport.

    python -m aether.cli windows
    python -m aether.cli cdp
    python -m aether.cli lease status
    python -m aether.cli lease acquire --agent grok --task "focus exo"
    python -m aether.cli lease release --token TOKEN
    python -m aether.cli script steps.json
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Dict, List, Optional

from aether.exec_engine import AetherExecEngine
from aether.smart import SmartController


def _emit(obj: Any) -> None:
    print(json.dumps(obj, indent=2, default=str))


def run_steps(ctrl: SmartController, steps: List[Dict[str, Any]]) -> Dict[str, Any]:
    return AetherExecEngine(controller=ctrl).execute(steps)


def main(argv: Optional[List[str]] = None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    ap = argparse.ArgumentParser(prog="aether.cli")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("windows")
    sub.add_parser("stats")
    sub.add_parser("cdp")

    p = sub.add_parser("focus")
    p.add_argument("title")

    p = sub.add_parser("read")
    p.add_argument("title", nargs="?")
    p.add_argument("--interactive", action="store_true")
    p.add_argument("--max", type=int, default=120)

    p = sub.add_parser("click")
    p.add_argument("title")
    p.add_argument("query")
    p.add_argument("--require-change", action="store_true")

    p = sub.add_parser("verify")
    p.add_argument("title")
    p.add_argument("--expect", nargs="*", default=[])
    p.add_argument("--gone", nargs="*", default=[])
    p.add_argument("--timeout", type=float, default=6.0)

    p = sub.add_parser("script")
    p.add_argument("path")

    p = sub.add_parser("shot")
    p.add_argument("title")
    p.add_argument("out")

    p = sub.add_parser("lease")
    lease_sub = p.add_subparsers(dest="lease_cmd", required=True)
    lease_sub.add_parser("status")
    p_acq = lease_sub.add_parser("acquire")
    p_acq.add_argument("--agent", required=True)
    p_acq.add_argument("--task", default="")
    p_acq.add_argument("--ttl", type=float, default=120)
    p_rel = lease_sub.add_parser("release")
    p_rel.add_argument("--token", required=True)

    args = ap.parse_args(argv)

    if args.cmd == "cdp":
        from aether import exo_bridge
        endpoints = exo_bridge.discover_cdp_endpoints()
        _emit({"ok": True, "endpoints": endpoints, "count": len(endpoints)})
        return 0

    if args.cmd == "lease":
        from aether import desktop_lease
        if args.lease_cmd == "status":
            _emit(desktop_lease.status())
            return 0
        if args.lease_cmd == "acquire":
            _emit(desktop_lease.acquire(agent_id=args.agent, task=args.task, ttl_sec=args.ttl))
            return 0
        if args.lease_cmd == "release":
            out = desktop_lease.release(token=args.token)
            _emit(out)
            return 0 if out.get("ok") else 1

    ctrl = SmartController(prefer_cua=False, verify=True)

    if args.cmd == "windows":
        _emit(ctrl.list_windows())
        return 0
    if args.cmd == "stats":
        _emit(ctrl.stats())
        return 0
    if args.cmd == "script":
        with open(args.path, "r", encoding="utf-8") as fh:
            steps = json.load(fh)
        _emit(run_steps(ctrl, steps))
        return 0

    if getattr(args, "title", None):
        focus = ctrl.smart_focus(title=args.title)
        if not focus.get("ok"):
            _emit(focus)
            return 1

    if args.cmd == "shot":
        state = ctrl.window_state(ctrl._focus_window_id)
        rect = state.get("rect") if state.get("known") else None
        img = ctrl.perception.capture(monitor=1, region=tuple(rect) if rect else None)
        if img is None:
            _emit({"ok": False, "error": "capture failed"})
            return 1
        img.save(args.out)
        _emit({"ok": True, "path": args.out, "size": list(img.size), "window": state})
        return 0

    if args.cmd == "focus":
        _emit(focus)
    elif args.cmd == "read":
        _emit(ctrl.read_ui(force=True, interactive_only=args.interactive,
                           max_elements=args.max))
    elif args.cmd == "click":
        r = ctrl.smart_click(query=args.query, require_change=args.require_change)
        _emit({"success": r.success, "verified": r.verified, "message": r.message,
               "elapsed": round(r.elapsed, 3)})
        return 0 if r.success else 1
    elif args.cmd == "verify":
        out = ctrl.verify_ui(expect=args.expect, expect_gone=args.gone,
                             timeout=args.timeout)
        _emit(out)
        return 0 if out["ok"] else 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
