"""Break down where a UIA tree build spends its time."""
from __future__ import annotations

import sys
import time

from aether.uia_cache import enum_top_windows, get_fast_uia, get_uia_cache


def main(hint: str) -> None:
    win = None
    for w in enum_top_windows():
        if hint.lower() in (w["title"] or "").lower():
            win = w
            break
    if win is None:
        print("no window")
        return
    print(f"window {win['title']!r} hwnd={win['handle']}")

    fast = get_fast_uia()
    print("fast uia ok:", fast.ok)

    t = time.time()
    root = fast.element_from_handle(win["handle"])
    print(f"ElementFromHandle: {time.time() - t:.3f}s")

    for scope_name, scope in (("descendants", 4), ("children", 2), ("subtree", 7)):
        t = time.time()
        try:
            arr = root.FindAllBuildCache(scope, fast._condition, fast._cache_req)
            n = int(arr.Length)
            build = time.time() - t
        except Exception as e:
            print(f"{scope_name}: FAILED {e}")
            continue
        t = time.time()
        raws = [arr.GetElement(i) for i in range(min(n, 400))]
        fetch = time.time() - t
        t = time.time()
        for r in raws:
            fast.read(r)
        read = time.time() - t
        print(f"{scope_name}: count={n} FindAll={build:.3f}s GetElement={fetch:.3f}s "
              f"read={read:.3f}s total={build + fetch + read:.3f}s")

    cache = get_uia_cache()
    for i in range(3):
        t = time.time()
        tree = cache.get_tree(win["pid"], win["handle"], force=True)
        print(f"get_tree #{i}: {time.time() - t:.3f}s elements={len(tree.elements)} "
              f"truncated={tree.truncated} build_ms={tree.build_ms}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "Exo")
