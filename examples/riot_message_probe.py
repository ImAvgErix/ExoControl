"""Confirm Exo explains itself when Riot needs the user, and keeps saying so."""
from __future__ import annotations

import time

from aether.smart import SmartController


def status_texts(ctrl: SmartController) -> list[str]:
    ui = ctrl.read_ui(force=True, max_elements=140)
    return [e["name"] for e in ui["elements"]
            if "sign in" in e["name"].lower() or "Riot Client" in e["name"]
            or "press Play" in e["name"]]


def main() -> int:
    ctrl = SmartController(prefer_cua=False)
    ctrl.smart_focus(title="Exo Launcher")

    ctrl.smart_click(query="League of Legends", require_change=True)
    time.sleep(1.0)
    play = ctrl.smart_click(query="Play")
    print("play:", play.success, play.message[:60])

    msg = None
    deadline = time.time() + 130
    while time.time() < deadline:
        found = status_texts(ctrl)
        if found:
            msg = found
            print(f"[{130 - (deadline - time.time()):5.1f}s] message shown: {found}")
            break
        time.sleep(1.5)

    if msg is None:
        print("FAIL: Exo never explained why the launch stopped")
        return 1

    for wait in (6, 12):
        time.sleep(6)
        still = status_texts(ctrl)
        print(f"  after {wait}s still shown: {bool(still)} {still}")
        if not still:
            print("FAIL: actionable message vanished on a timer")
            return 1

    st = ctrl.window_state(ctrl._focus_window_id)
    ctrl.perception.capture(monitor=1, region=tuple(st["rect"])).save(
        r"C:\Users\Erix\Documents\exo-launcher\docs\media\verify-riot.png")
    print("PASS: message persisted; screenshot saved")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
