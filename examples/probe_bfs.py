"""Measure level-by-level BFS cost and where the useful controls live."""
from __future__ import annotations

import sys
import time

from aether.uia_cache import INTERACTIVE_ROLES, enum_top_windows, get_fast_uia


def main(hint: str) -> None:
    win = next((w for w in enum_top_windows() if hint.lower() in (w["title"] or "").lower()), None)
    if not win:
        print("no window")
        return
    fast = get_fast_uia()
    root = fast.element_from_handle(win["handle"])

    frontier = [root]
    total_time = 0.0
    total_nodes = 0
    named_total = 0
    interactive_total = 0
    for depth in range(1, 16):
        t = time.time()
        nxt = []
        for node in frontier:
            try:
                arr = node.FindAllBuildCache(2, fast._condition, fast._cache_req)
                for i in range(int(arr.Length)):
                    nxt.append(arr.GetElement(i))
            except Exception:
                continue
        dt = time.time() - t
        total_time += dt
        if not nxt:
            print(f"depth {depth}: empty, stop")
            break
        named = 0
        interactive = 0
        samples = []
        for el in nxt:
            r = fast.read(el)
            if not r:
                continue
            name, role, _bbox, _on, _en, _aid = r
            if name:
                named += 1
                if len(samples) < 4:
                    samples.append(f"{role}:{name[:22]}")
            if (role or "").lower() in INTERACTIVE_ROLES:
                interactive += 1
        total_nodes += len(nxt)
        named_total += named
        interactive_total += interactive
        print(f"depth {depth:<2} nodes={len(nxt):<5} named={named:<4} interactive={interactive:<4} "
              f"{dt:.3f}s cum={total_time:.3f}s  {samples}")
        if total_time > 6.0:
            print("... time budget hit")
            break
        frontier = nxt

    print(f"TOTAL nodes={total_nodes} named={named_total} interactive={interactive_total} "
          f"time={total_time:.3f}s")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "Exo")
