"""Benchmark Aether eyes against a live window. Usage: python bench_eyes.py [title-substring]"""
from __future__ import annotations

import statistics
import sys
import time

from aether.smart import SmartController


def bench(title_hint: str, rounds: int = 6) -> None:
    ctrl = SmartController(prefer_cua=False, verify=True)

    t0 = time.time()
    windows = ctrl.list_windows()
    print(f"list_windows: {len(windows)} visible in {time.time() - t0:.3f}s")

    match = None
    for w in windows:
        if title_hint.lower() in (w.get("title") or "").lower():
            match = w
            break
    if match is None:
        print(f"no window matching {title_hint!r}; candidates:")
        for w in windows[:20]:
            print("   ", w.get("pid"), repr(w.get("title"))[:70])
        return

    print(f"target: pid={match['pid']} hwnd={match['handle']} {match['title']!r}")
    ctrl.focus_window(int(match["pid"]), int(match["handle"]))

    cold = []
    warm = []
    for i in range(rounds):
        t = time.time()
        ui = ctrl.read_ui(force=True)
        cold.append(time.time() - t)
        t = time.time()
        ui_warm = ctrl.read_ui(force=False)
        warm.append(time.time() - t)
        if i == 0:
            labels = ui.get("labels") or []
            uniq = list(dict.fromkeys(labels))
            print(f"labels={len(labels)} unique={len(uniq)} duplication={len(labels) - len(uniq)}")
            print(f"elements returned={len(ui.get('elements') or [])} total={ui.get('element_count')}")
            print(f"ui_hash={ui.get('ui_hash')} title={ui.get('title')!r}")
            print("first 25 labels:", uniq[:25])
            print("warm keys:", sorted(ui_warm.keys()))

    print(f"read_ui cold: p50={statistics.median(cold):.3f}s max={max(cold):.3f}s")
    print(f"read_ui warm: p50={statistics.median(warm):.3f}s max={max(warm):.3f}s")

    t = time.time()
    targets = ctrl.find_targets("Library")
    print(f"find_targets('Library'): {len(targets)} in {time.time() - t:.3f}s")
    for tg in targets[:6]:
        role = (tg.meta or {}).get("role")
        print(f"    {tg.confidence:.2f} {role or '?':<12} {tg.label!r:<40} @({tg.x},{tg.y}) src={tg.source}")


if __name__ == "__main__":
    bench(sys.argv[1] if len(sys.argv) > 1 else "Exo")
