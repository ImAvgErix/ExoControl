"""End-to-end Aether check against the running Exo window."""
from __future__ import annotations

import json
import sys
import time

from aether.smart import SmartController


def main(hint: str) -> int:
    ctrl = SmartController(prefer_cua=False, verify=True)
    focus = ctrl.smart_focus(title=hint)
    print("smart_focus:", json.dumps(focus, default=str))
    if not focus.get("ok"):
        return 1
    if not focus.get("raised"):
        print("!! window did not come to the foreground")

    ui = ctrl.read_ui(force=True, interactive_only=True)
    print(f"interactive controls={ui['interactive_count']} of {ui['element_count']} "
          f"offscreen={ui['offscreen_count']} in {ui['elapsed']}s")
    for e in ui["elements"][:14]:
        print(f"   {e['role']:<10} {e['name'][:40]:<42} on_screen={e['on_screen']}")

    print("\n-- verify_ui baseline --")
    print(json.dumps(ctrl.verify_ui(expect=["Settings", "Home library"], timeout=3.0),
                     default=str)[:400])

    print("\n-- click Settings (require_change) --")
    out = ctrl.smart_click(query="Settings", require_change=True)
    print(f"success={out.success} verified={out.verified} {out.message} ({out.elapsed:.2f}s)")

    time.sleep(0.6)
    v = ctrl.verify_ui(expect=["Backends"], timeout=4.0)
    print("settings visible:", v["ok"], v.get("found") or v.get("missing"))

    print("\n-- click back to library --")
    back = ctrl.smart_click(query="Home library", require_change=True)
    print(f"success={back.success} verified={back.verified} {back.message} ({back.elapsed:.2f}s)")
    v2 = ctrl.verify_ui(expect=["PINNED"], expect_gone=["Backends"], timeout=4.0)
    print("library restored:", v2["ok"], "missing:", v2["missing"],
          "still:", v2["still_present"])

    print("\n-- hotkey alias --")
    hk = ctrl.smart_hotkey(["ESCAPE"])
    print(f"ESCAPE -> success={hk.success} {hk.message}")

    print("\n-- offscreen guard --")
    guard = ctrl.smart_click(x=-30861, y=-31528)
    print(f"offscreen click success={guard.success} (want False): {guard.message}")

    print("\n-- stats --")
    print(json.dumps(ctrl.stats(), indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "Exo Launcher"))
