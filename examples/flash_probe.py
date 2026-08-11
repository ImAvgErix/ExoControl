"""Measure whether any store-client window becomes visible during an Exo launch.

Samples top-level windows at ~40Hz while driving Play, so a flash short enough
to be missed by eye still shows up as a nonzero visible duration.
"""
from __future__ import annotations

import sys
import threading
import time

from aether.smart import SmartController
from aether.uia_cache import enum_top_windows

STORE_HINTS = ("steam", "epicgameslauncher", "epicwebhelper", "galaxyclient",
               "riot client", "riotclient")

stop = threading.Event()
sightings: list[tuple[float, str, str, list[int]]] = []
samples = 0


def is_store(title: str, cls: str) -> bool:
    blob = f"{title} {cls}".lower()
    return any(h in blob for h in STORE_HINTS)


def sampler(t0: float) -> None:
    global samples
    while not stop.is_set():
        samples += 1
        try:
            for w in enum_top_windows(visible_only=True):
                title = w.get("title") or ""
                cls = w.get("class_name") or ""
                if not is_store(title, cls):
                    continue
                r = w.get("rect") or [0, 0, 0, 0]
                if r[2] - r[0] < 80 or r[3] - r[1] < 60:
                    continue  # zero/'1x1' helper surfaces are not a visible flash
                sightings.append((round(time.time() - t0, 3), title, cls, r))
        except Exception:
            pass
        time.sleep(0.04)


def main(game: str) -> int:
    ctrl = SmartController(prefer_cua=False)
    focus = ctrl.smart_focus(title="Exo Launcher")
    if not focus.get("ok"):
        print("Exo not found")
        return 1

    # Offscreen cards are filtered out of the a11y tree, so bring the grid home.
    state = ctrl.window_state(ctrl._focus_window_id)
    if state.get("known"):
        l, t, r, b = state["rect"]
        ctrl.local_fallback.engine.move((l + r) // 2, (t + b) // 2)
        for _ in range(8):
            ctrl.local_fallback.engine.scroll(dx=0, dy=600)
            time.sleep(0.12)
        time.sleep(0.6)

    print(f"opening {game!r}")
    out = ctrl.smart_click(query=game, require_change=True)
    print("  card click:", out.success, out.message[:80])
    time.sleep(1.0)

    ui = ctrl.read_ui(force=True, interactive_only=True, max_elements=60)
    actions = [e["name"] for e in ui["elements"]
               if e["name"] in ("Play", "Install", "Update", "Stop", "Cancel")]
    print("  detail actions:", actions)
    if "Play" not in actions:
        print("  no Play button; aborting without launching")
        return 2

    t0 = time.time()
    thread = threading.Thread(target=sampler, args=(t0,), daemon=True)
    thread.start()

    launch = ctrl.smart_click(query="Play")
    print("  play click:", launch.success, launch.message[:80])

    deadline = time.time() + 45
    game_pid = None
    while time.time() < deadline:
        for w in enum_top_windows(visible_only=True):
            title = (w.get("title") or "").lower()
            if game.lower()[:12] in title and not is_store(title, ""):
                game_pid = w.get("pid")
                break
        if game_pid:
            break
        time.sleep(0.3)

    time.sleep(2.0)
    stop.set()
    thread.join(timeout=2)

    print(f"\nsamples={samples} over {time.time() - t0:.1f}s")
    if not sightings:
        print("RESULT: no store window was ever visible — no flash")
    else:
        first, last = sightings[0][0], sightings[-1][0]
        print(f"RESULT: store window visible in {len(sightings)} samples "
              f"({first}s..{last}s ≈ {(last - first) + 0.04:.2f}s of screen time)")
        seen = {}
        for ts, title, cls, rect in sightings:
            seen.setdefault((title, cls), []).append(ts)
        for (title, cls), times in seen.items():
            print(f"   {title!r} [{cls}] x{len(times)} first={times[0]}s")
    print("game window pid:", game_pid)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "Beast of Reincarnation"))
