"""Compare UIA condition strategies for cost vs coverage."""
from __future__ import annotations

import sys
import time

from pywinauto.uia_defines import IUIA

from aether.uia_cache import enum_top_windows, get_fast_uia

INTERESTING = [
    "Button", "MenuItem", "TabItem", "ListItem", "Hyperlink", "Edit", "CheckBox",
    "RadioButton", "ComboBox", "SplitButton", "TreeItem", "Text", "Image", "Document",
]


def main(hint: str) -> None:
    win = next((w for w in enum_top_windows() if hint.lower() in (w["title"] or "").lower()), None)
    if not win:
        print("no window")
        return
    fast = get_fast_uia()
    iuia = fast.iuia
    dll = IUIA().UIA_dll
    root = fast.element_from_handle(win["handle"])
    req = fast._cache_req
    not_offscreen = iuia.CreateNotCondition(
        iuia.CreatePropertyCondition(dll.UIA_IsOffscreenPropertyId, True))

    def run(name, cond, req_override=None):
        t = time.time()
        try:
            arr = root.FindAllBuildCache(4, cond, req_override or req)
            n = int(arr.Length)
        except Exception as e:
            print(f"{name:<34} FAILED {e}")
            return
        dt = time.time() - t
        named = 0
        for i in range(min(n, 500)):
            try:
                if (arr.GetElement(i).CachedName or "").strip():
                    named += 1
            except Exception:
                pass
        print(f"{name:<34} count={n:<6} named(first500)={named:<5} {dt:.3f}s")

    run("NOT offscreen", not_offscreen)

    try:
        content = iuia.ContentViewCondition
        run("content view", content)
        run("content AND NOT offscreen",
            iuia.CreateAndCondition(content, not_offscreen))
    except Exception as e:
        print("content view unavailable:", e)

    ors = []
    for name in INTERESTING:
        try:
            ors.append(iuia.CreatePropertyCondition(
                dll.UIA_ControlTypePropertyId, getattr(dll, f"UIA_{name}ControlTypeId")))
        except Exception:
            pass
    combo = ors[0]
    for c in ors[1:]:
        combo = iuia.CreateOrCondition(combo, c)
    run("interesting control types", combo)
    run("interesting AND NOT offscreen", iuia.CreateAndCondition(combo, not_offscreen))

    ctrl_only = []
    for name in ["Button", "MenuItem", "TabItem", "ListItem", "Hyperlink", "Edit",
                 "CheckBox", "RadioButton", "ComboBox", "SplitButton", "TreeItem"]:
        try:
            ctrl_only.append(iuia.CreatePropertyCondition(
                dll.UIA_ControlTypePropertyId, getattr(dll, f"UIA_{name}ControlTypeId")))
        except Exception:
            pass
    c2 = ctrl_only[0]
    for c in ctrl_only[1:]:
        c2 = iuia.CreateOrCondition(c2, c)
    run("interactive only", iuia.CreateAndCondition(c2, not_offscreen))

    # Does a smaller cache request help?
    lean = iuia.CreateCacheRequest()
    lean.AddProperty(dll.UIA_NamePropertyId)
    lean.AddProperty(dll.UIA_ControlTypePropertyId)
    lean.AddProperty(dll.UIA_BoundingRectanglePropertyId)
    run("NOT offscreen (lean cache)", not_offscreen, lean)

    try:
        lean2 = iuia.CreateCacheRequest()
        lean2.AddProperty(dll.UIA_NamePropertyId)
        lean2.AddProperty(dll.UIA_ControlTypePropertyId)
        lean2.AddProperty(dll.UIA_BoundingRectanglePropertyId)
        lean2.TreeFilter = iuia.ContentViewCondition
        run("content-filtered cache req", not_offscreen, lean2)
    except Exception as e:
        print("tree filter unavailable:", e)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "Exo")
