"""Minimal Exo Control loop — same engine as MCP / CLI."""
from __future__ import annotations

from exo_control import ExoExecEngine


def main() -> None:
    eng = ExoExecEngine()
    print(eng.execute([{"op": "status"}]).get("steps", [{}])[0].get("result", {}).get("version"))
    print(eng.execute([{"op": "help"}]).get("ok"))


if __name__ == "__main__":
    main()
