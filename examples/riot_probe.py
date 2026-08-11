"""Drive a Riot launch from Exo and report the honest outcome.

Either the game process appears, or Exo must surface the Riot Client and say so
— the previous behaviour was to keep it hidden and stall forever.
"""
from __future__ import annotations

import sys
import time

from aether.smart import SmartController
from aether.uia_cache import enum_top_windows

GAME_HINTS = ("league of legends", "valorant", "riot client")


def visible_riot_windows() -> list[dict]:
    out = []
    for w in enum_top_windows(visible_only=True):
        title = (w.get("title") or "").lower()
        r = w.get("rect") or [0, 0, 0, 0]
        if r[2] - r[0] < 200 or r[3] - r[1] < 150:
            continue
        if any(h in title for h in GAME_HINTS):
            out.append(w)
    return out


def main(game: str) -> int:
    ctrl = SmartController(prefer_cua=False)
    if not ctrl.smart_focus(title="Exo Launcher").get("ok"):
        print("Exo not running")
        return 1

    print("visible riot windows before:", [w["title"] for w in visible_riot_windows()])

    out = ctrl.smart_click(query=game, require_change=True)
    print(f"card click: {out.success} {out.message[:70]}")
    time.sleep(1.0)

    ui = ctrl.read_ui(force=True, interactive_only=True, max_elements=60)
    actions = [e["name"] for e in ui["elements"]
               if e["name"] in ("Play", "Install", "Update", "Cancel")]
    print("detail actions:", actions)
    if "Play" not in actions:
        print("no Play button")
        return 2

    launch = ctrl.smart_click(query="Play")
    print(f"play click: {launch.success} {launch.message[:70]}")

    # Watch what Exo reports and what becomes visible.
    deadline = time.time() + 100
    last_status = ""
    revealed = []
    while time.time() < deadline:
        tree = ctrl.read_ui(force=True, max_elements=120)
        texts = [e["name"] for e in tree["elements"]]
        status = next((t for t in texts if "Riot" in t or "sign in" in t.lower()
                       or "Running" in t or "Launching" in t or "Starting" in t), "")
        if status and status != last_status:
            print(f"  [{time.time() - (deadline - 100):5.1f}s] exo says: {status[:90]}")
            last_status = status
        vis = visible_riot_windows()
        if vis and not revealed:
            revealed = [w["title"] for w in vis]
            print(f"  riot window revealed: {revealed}")
        if any("league" in (w.get("title") or "").lower() for w in enum_top_windows()):
            break
        time.sleep(1.2)

    print("\nfinal visible riot windows:", [w["title"] for w in visible_riot_windows()])
    procs = [w["title"] for w in enum_top_windows(visible_only=True)
             if (w.get("title") or "").strip()]
    print("all visible titles:", procs)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "League of Legends"))
