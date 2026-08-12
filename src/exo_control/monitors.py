"""Multi-monitor helpers — bind observe/focus/shot to a physical display."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple


def _mss_session():
    import mss
    return getattr(mss, "MSS", mss.mss)()


def list_monitor_dicts() -> List[Dict[str, Any]]:
    """Return physical monitors (mss index style: id starts at 1)."""
    try:
        with _mss_session() as sct:
            out: List[Dict[str, Any]] = []
            for i, mon in enumerate(sct.monitors):
                if i == 0:
                    continue  # virtual "all"
                out.append(
                    {
                        "id": i,
                        "left": int(mon["left"]),
                        "top": int(mon["top"]),
                        "width": int(mon["width"]),
                        "height": int(mon["height"]),
                        "right": int(mon["left"]) + int(mon["width"]),
                        "bottom": int(mon["top"]) + int(mon["height"]),
                    }
                )
            return out
    except Exception:
        return [
            {
                "id": 1,
                "left": 0,
                "top": 0,
                "width": 1920,
                "height": 1080,
                "right": 1920,
                "bottom": 1080,
            }
        ]


def get_monitor(monitor_id: int) -> Optional[Dict[str, Any]]:
    mons = list_monitor_dicts()
    for m in mons:
        if int(m["id"]) == int(monitor_id):
            return m
    return None


def _as_rect(rect: Any) -> Optional[Tuple[int, int, int, int]]:
    if rect is None:
        return None
    if isinstance(rect, dict):
        left = rect.get("left", rect.get("x"))
        top = rect.get("top", rect.get("y"))
        right = rect.get("right")
        bottom = rect.get("bottom")
        if right is None and left is not None and rect.get("width") is not None:
            right = int(left) + int(rect["width"])
        if bottom is None and top is not None and rect.get("height") is not None:
            bottom = int(top) + int(rect["height"])
        if None in (left, top, right, bottom):
            return None
        return int(left), int(top), int(right), int(bottom)
    if isinstance(rect, (list, tuple)) and len(rect) >= 4:
        return int(rect[0]), int(rect[1]), int(rect[2]), int(rect[3])
    return None


def rect_center(rect: Sequence[int]) -> Tuple[float, float]:
    l, t, r, b = rect
    return (l + r) / 2.0, (t + b) / 2.0


def point_in_monitor(x: float, y: float, mon: Dict[str, Any]) -> bool:
    return (
        mon["left"] <= x < mon["right"]
        and mon["top"] <= y < mon["bottom"]
    )


def rect_on_monitor(
    rect: Any,
    mon: Dict[str, Any],
    *,
    require_center: bool = True,
    min_overlap: float = 0.35,
) -> bool:
    """True if window rect belongs on the given monitor."""
    rr = _as_rect(rect)
    if rr is None:
        return False
    l, t, r, b = rr
    if require_center:
        cx, cy = rect_center(rr)
        if point_in_monitor(cx, cy, mon):
            return True
    # overlap area ratio vs window
    ol = max(l, mon["left"])
    ot = max(t, mon["top"])
    orr = min(r, mon["right"])
    ob = min(b, mon["bottom"])
    if orr <= ol or ob <= ot:
        return False
    inter = (orr - ol) * (ob - ot)
    area = max(1, (r - l) * (b - t))
    return (inter / area) >= min_overlap


def window_on_monitor(window: Dict[str, Any], mon: Dict[str, Any]) -> bool:
    rect = window.get("rect") or window.get("bbox") or window.get("bounds")
    return rect_on_monitor(rect, mon)


def filter_windows_for_monitor(
    windows: List[Dict[str, Any]],
    monitor_id: int,
) -> Tuple[List[Dict[str, Any]], Optional[Dict[str, Any]]]:
    mon = get_monitor(int(monitor_id))
    if mon is None:
        return [], None
    hits = [w for w in windows if window_on_monitor(w, mon)]
    return hits, mon


def monitor_bind_error(monitor_id: int, detail: str) -> Dict[str, Any]:
    return {
        "ok": False,
        "error": f"monitor bind failed: {detail}",
        "monitor": int(monitor_id),
        "monitors": list_monitor_dicts(),
    }
