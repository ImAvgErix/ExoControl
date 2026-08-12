"""Drive Exo Control from a shell — any harness that can run a process.

    exo-control windows
    exo-control ops
    exo-control help [query]
    exo-control exec --steps '[{"op":"help"}]'
    exo-control exec < steps.json
    exo-control script steps.json
    exo-control mcp
    exo-control lease status
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Dict, List, Optional

from aether.exec_engine import ExoExecEngine
from aether.ops_catalog import list_ops
from aether.smart import SmartController


def _emit(obj: Any) -> None:
    print(json.dumps(obj, indent=2, default=str))


def run_steps(ctrl: SmartController, steps: List[Dict[str, Any]]) -> Dict[str, Any]:
    return ExoExecEngine(controller=ctrl).execute(steps)


def main(argv: Optional[List[str]] = None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    ap = argparse.ArgumentParser(
        prog="exo-control",
        description="Exo Control CLI — eyes/hands for any AI harness (JSON in/out).",
    )
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("windows", help="List top-level windows")
    sub.add_parser("stats", help="Driver stats")
    sub.add_parser("cdp", help="Discover CDP endpoints")
    sub.add_parser("monitors", help="List physical monitors")
    p_ops = sub.add_parser("ops", help="Op catalog for any AI")
    p_ops.add_argument("query", nargs="?", default=None)
    p_ops.add_argument("--detail", action="store_true")
    p_help = sub.add_parser("help", help="Same as ops (agent-friendly)")
    p_help.add_argument("query", nargs="?", default=None)
    p_help.add_argument("--detail", action="store_true")

    p = sub.add_parser("focus")
    p.add_argument("title")
    p.add_argument("--monitor", type=int, default=None)

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

    p = sub.add_parser("script", help="Run a JSON steps file")
    p.add_argument("path")

    p = sub.add_parser("exec", help="Run JSON steps from --steps or stdin")
    p.add_argument("--steps", default=None, help="JSON array string")
    p.add_argument("--file", "-f", default=None, help="JSON file path")
    p.add_argument("--continue-on-fail", action="store_true")

    p = sub.add_parser("shot")
    p.add_argument("title")
    p.add_argument("out")
    p.add_argument("--monitor", type=int, default=1)

    p = sub.add_parser("mcp", help="Run the MCP stdio server (any MCP host)")
    p.add_argument("--module", default="exo_control.slim_mcp_server",
                   help="Python module (default exo_control.slim_mcp_server)")

    sub.add_parser("doctor", help="Diagnose install path / dual package shadowing")

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

    if args.cmd == "mcp":
        import runpy
        # stdio MCP server
        sys.argv = [args.module]
        runpy.run_module(args.module, run_name="__main__")
        return 0

    if args.cmd == "doctor":
        import aether
        import exo_control
        from pathlib import Path
        from aether.paths import exo_root, state_dir, lock_dir, workspace_dir
        aether_path = Path(getattr(aether, "__file__", "") or "")
        exo_path = Path(getattr(exo_control, "__file__", "") or "")
        warnings: List[str] = []
        path_entries = [Path(p) for p in sys.path if p]
        aether_srcs = [str(p) for p in path_entries if "aether-driver" in str(p) or "ExoControl" in str(p)]
        if any("aether-driver" in p for p in aether_srcs) and any("ExoControl" in p for p in aether_srcs):
            if "aether-driver" in str(aether_path):
                warnings.append(
                    "import resolves to ~/.aether/aether-driver — remove leftover "
                    "__editable__.aether_driver-*.pth or drop PYTHONPATH so pip install wins"
                )
        site = Path(sys.prefix) / "Lib" / "site-packages"
        stale = list(site.glob("__editable__.aether_driver-*.pth")) if site.exists() else []
        for pth in stale:
            warnings.append(f"stale editable pth: {pth}")
        _emit({
            "ok": len(warnings) == 0,
            "version": getattr(aether, "__version__", "?"),
            "engine": "ExoExecEngine",
            "aether": str(aether_path),
            "exo_control": str(exo_path),
            "exo_root": str(exo_root()),
            "state_dir": str(state_dir()),
            "lock_dir": str(lock_dir()),
            "workspace": str(workspace_dir()),
            "same_tree": aether_path.parent.parent == exo_path.parent.parent if aether_path and exo_path else False,
            "sys_path_hits": aether_srcs[:8],
            "warnings": warnings,
            "hint": "pip install \"git+https://github.com/ImAvgErix/ExoControl.git\"  (or pip install -e .)",
        })
        return 0 if not warnings else 1

    if args.cmd == "cdp":
        from aether import exo_bridge
        endpoints = exo_bridge.discover_cdp_endpoints()
        _emit({"ok": True, "endpoints": endpoints, "count": len(endpoints)})
        return 0

    if args.cmd in {"ops", "help"}:
        _emit(list_ops(query=getattr(args, "query", None), detail=bool(getattr(args, "detail", False))))
        return 0

    if args.cmd == "monitors":
        from aether.monitors import list_monitor_dicts
        mons = list_monitor_dicts()
        _emit({"ok": True, "monitors": mons, "count": len(mons)})
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

    if args.cmd == "exec":
        raw = args.steps
        if args.file:
            with open(args.file, "r", encoding="utf-8") as fh:
                raw = fh.read()
        if raw is None:
            if sys.stdin.isatty():
                _emit({"ok": False, "error": "pass --steps JSON, --file path, or pipe JSON on stdin"})
                return 2
            raw = sys.stdin.read()
        eng = ExoExecEngine()
        out = eng.execute(raw, stop_on_failure=not args.continue_on_fail)
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
        mon = getattr(args, "monitor", None)
        focus = ctrl.smart_focus(title=args.title, monitor=mon)
        if not focus.get("ok"):
            _emit(focus)
            return 1
    else:
        focus = None

    if args.cmd == "shot":
        eng = ExoExecEngine(controller=ctrl)
        out = eng.screenshot(title=args.title, monitor=int(getattr(args, "monitor", 1) or 1))
        if not out.get("ok"):
            _emit(out)
            return 1
        # If path requested via legacy CLI, write via perception when base64 present
        # Prefer path write from capture
        state = ctrl.window_state(ctrl._focus_window_id)
        rect = state.get("rect") if state.get("known") else None
        img = ctrl.perception.capture(
            monitor=int(getattr(args, "monitor", 1) or 1),
            region=tuple(rect) if rect else None,
        )
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
