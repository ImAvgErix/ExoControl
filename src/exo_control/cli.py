"""Drive Exo Control from a shell — any harness that can run a process.

    exo-control windows
    exo-control ops
    exo-control help [query]
    exo-control exec --steps '[{"op":"help"}]'
    exo-control exec < steps.json
    exo-control script steps.json
    exo-control mcp
    exo-control lease status
    exo-control doctor
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Dict, List, Optional

from exo_control.ops_catalog import list_ops
from exo_control.policy import identity, sanitize_cdp_endpoints, shadow_warnings


def _emit(obj: Any) -> None:
    print(json.dumps(obj, indent=2, default=str))


def _exec(steps: List[Dict[str, Any]], *, auto_lease: bool = False) -> Dict[str, Any]:
    from exo_control.exec_engine import ExoExecEngine

    if auto_lease:
        steps = [
            {"op": "lease_acquire", "agent_id": "cli", "task": "cli", "ttl_sec": 120},
            *steps,
            {"op": "lease_release"},
        ]
    return ExoExecEngine().execute(steps)


def main(argv: Optional[List[str]] = None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    if not argv:
        _emit(list_ops(detail=False))
        return 0

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
        sys.argv = [args.module]
        runpy.run_module(args.module, run_name="__main__")
        return 0

    if args.cmd == "doctor":
        import aether
        import exo_control
        from pathlib import Path
        from exo_control.paths import exo_root, lock_dir, state_dir, workspace_dir

        aether_path = Path(getattr(aether, "__file__", "") or "")
        exo_path = Path(getattr(exo_control, "__file__", "") or "")
        warnings = shadow_warnings(aether_file=str(exo_path))
        ident = identity()
        _emit({
            "ok": len(warnings) == 0,
            **ident,
            "aether": str(aether_path),
            "exo_control": str(exo_path),
            "exo_root": str(exo_root()),
            "state_dir": str(state_dir()),
            "lock_dir": str(lock_dir()),
            "workspace": str(workspace_dir()),
            "same_tree": (
                aether_path.parent.parent == exo_path.parent.parent
                if aether_path and exo_path else False
            ),
            "warnings": warnings,
            "hint": "pip install \"git+https://github.com/ImAvgErix/ExoControl.git@v2.0.0\"",
        })
        return 0 if not warnings else 1

    if args.cmd == "cdp":
        from exo_control import exo_bridge
        endpoints = sanitize_cdp_endpoints(exo_bridge.discover_cdp_endpoints())
        _emit({"ok": True, "endpoints": endpoints, "count": len(endpoints)})
        return 0

    if args.cmd in {"ops", "help"}:
        _emit(list_ops(
            query=getattr(args, "query", None),
            detail=bool(getattr(args, "detail", False)),
        ))
        return 0

    if args.cmd == "monitors":
        out = _exec([{"op": "monitors"}])
        _emit(out["steps"][0]["result"] if out.get("steps") else out)
        return 0 if out.get("ok") else 1

    if args.cmd == "lease":
        from exo_control import desktop_lease
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
        from exo_control.exec_engine import ExoExecEngine
        out = ExoExecEngine().execute(raw, stop_on_failure=not args.continue_on_fail)
        _emit(out)
        return 0 if out.get("ok") else 1

    if args.cmd == "script":
        with open(args.path, "r", encoding="utf-8") as fh:
            steps = json.load(fh)
        from exo_control.exec_engine import ExoExecEngine
        out = ExoExecEngine().execute(steps)
        _emit(out)
        return 0 if out.get("ok") else 1

    if args.cmd == "windows":
        out = _exec([{"op": "windows"}])
        _emit(out["steps"][0]["result"] if out.get("steps") else out)
        return 0 if out.get("ok") else 1

    if args.cmd == "stats":
        out = _exec([{"op": "stats"}])
        _emit(out["steps"][0]["result"] if out.get("steps") else out)
        return 0 if out.get("ok") else 1

    if args.cmd == "focus":
        step: Dict[str, Any] = {"op": "focus", "title": args.title}
        if args.monitor is not None:
            step["monitor"] = args.monitor
        out = _exec([step], auto_lease=True)
        _emit(out)
        return 0 if out.get("ok") else 1

    if args.cmd == "read":
        steps = []
        if args.title:
            steps.append({"op": "focus", "title": args.title})
        steps.append({
            "op": "read",
            "interactive": bool(args.interactive),
            "max_elements": int(args.max),
        })
        out = _exec(steps, auto_lease=bool(args.title))
        _emit(out)
        return 0 if out.get("ok") else 1

    if args.cmd == "click":
        out = _exec(
            [
                {"op": "focus", "title": args.title},
                {"op": "click", "query": args.query, "require_change": bool(args.require_change)},
            ],
            auto_lease=True,
        )
        _emit(out)
        return 0 if out.get("ok") else 1

    if args.cmd == "verify":
        steps = []
        if args.title:
            steps.append({"op": "focus", "title": args.title})
        steps.append({
            "op": "verify",
            "expect": list(args.expect or []),
            "expect_gone": list(args.gone or []),
            "timeout": float(args.timeout),
        })
        out = _exec(steps, auto_lease=bool(args.title))
        _emit(out)
        return 0 if out.get("ok") else 1

    if args.cmd == "shot":
        out = _exec(
            [
                {"op": "screenshot", "title": args.title, "monitor": int(args.monitor or 1), "path": args.out},
            ],
            auto_lease=True,
        )
        _emit(out)
        return 0 if out.get("ok") else 1

    _emit({"ok": False, "error": f"unknown command: {args.cmd}"})
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
