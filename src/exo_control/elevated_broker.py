"""Elevated helper process entrypoint.

Do **not** launch the MCP as admin — UIPI breaks clicks on normal windows.
This process is the Highest-Available broker started by the logon task or
one UAC ``runas``.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Optional


def main(argv: Optional[list] = None) -> int:
    os.environ["EXO_ELEVATED_BROKER"] = "1"
    ap = argparse.ArgumentParser(prog="exo-control-elevated-broker")
    ap.add_argument("--serve", action="store_true", help="listen on loopback (default)")
    ap.add_argument("--install", action="store_true", help="register the logon task, then optionally serve")
    args = ap.parse_args(argv if argv is not None else sys.argv[1:])

    from exo_control import elevate

    if args.install:
        out = elevate.install_task()
        if not args.serve:
            print(json.dumps(out, indent=2, default=str))
            return 0 if out.get("ok") else 1
    return elevate.serve_forever()


if __name__ == "__main__":
    raise SystemExit(main())
