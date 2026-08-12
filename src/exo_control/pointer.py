"""Pointer / wheel math for human-like scrolling.

Positive ``notches`` means scroll the *page* down (see content further below),
the way a person rolls the wheel toward the desk.
"""
from __future__ import annotations

from typing import Any, Dict, Mapping, Optional, Sequence, Tuple

WHEEL_DELTA = 120
NOTCHES_NUDGE = 1
NOTCHES_LINE = 3
NOTCHES_HALF = 6
NOTCHES_PAGE = 10

_AMOUNT = {
    "nudge": NOTCHES_NUDGE,
    "tick": NOTCHES_NUDGE,
    "line": NOTCHES_LINE,
    "lines": NOTCHES_LINE,
    "half": NOTCHES_HALF,
    "page": NOTCHES_PAGE,
    "pg": NOTCHES_PAGE,
}


def amount_to_notches(amount: Any, default: int = NOTCHES_LINE) -> int:
    if amount is None:
        return default
    if isinstance(amount, (int, float)) and not isinstance(amount, bool):
        n = int(amount)
        return n if n != 0 else default
    key = str(amount).strip().lower()
    return _AMOUNT.get(key, default)


def notches_to_px(notches: int) -> int:
    return int(notches) * WHEEL_DELTA


def dy_to_notches(dy: int) -> int:
    """Map legacy ``dy`` to notches.

    ``|dy| <= 20`` is already notches. Larger values are treated as pixels
    (≈120 px per notch). Sign: positive = page down.
    """
    if dy == 0:
        return 0
    if abs(dy) <= 20:
        return int(dy)
    return int(dy / float(WHEEL_DELTA)) or (1 if dy > 0 else -1)


def parse_scroll(step: Mapping[str, Any]) -> Dict[str, int]:
    """Return ``{notches, h_notches}`` from a step dict."""
    direction = str(step.get("direction") or step.get("dir") or "").strip().lower()
    notches_in = step.get("notches")
    dy = step.get("dy")
    dx = step.get("dx")
    amount = step.get("amount")

    v = 0
    h = 0
    if notches_in is not None:
        v = int(notches_in)
    elif dy is not None:
        v = dy_to_notches(int(dy))
    elif direction in {"down", "south"}:
        v = amount_to_notches(amount)
    elif direction in {"up", "north"}:
        v = -amount_to_notches(amount)
    elif direction in {"right", "east"}:
        h = amount_to_notches(amount)
    elif direction in {"left", "west"}:
        h = -amount_to_notches(amount)
    else:
        v = amount_to_notches(amount) if amount is not None else NOTCHES_LINE

    if dx is not None and h == 0:
        h = dy_to_notches(int(dx))
    return {"notches": int(v), "h_notches": int(h)}


def viewport_from_rect(rect: Sequence[int], chrome_top: int = 80) -> Tuple[int, int, int, int]:
    """Inset a window rect so we aim at the document, not the title bar."""
    l, t, r, b = (int(rect[0]), int(rect[1]), int(rect[2]), int(rect[3]))
    t = t + max(0, int(chrome_top))
    if b - t < 80:
        t = int(rect[1])
    return l, t, r, b


def aim_point(rect: Sequence[int], *, chrome_top: int = 80) -> Tuple[int, int]:
    l, t, r, b = viewport_from_rect(rect, chrome_top=chrome_top)
    return (l + r) // 2, (t + b) // 2


def bbox_visible(
    bbox: Sequence[int],
    viewport: Sequence[int],
    margin: int = 48,
) -> bool:
    if len(bbox) < 4 or len(viewport) < 4:
        return False
    x1, y1, x2, y2 = (int(bbox[0]), int(bbox[1]), int(bbox[2]), int(bbox[3]))
    vl, vt, vr, vb = (int(viewport[0]), int(viewport[1]), int(viewport[2]), int(viewport[3]))
    cx = (x1 + x2) // 2
    cy = (y1 + y2) // 2
    return (vl + margin) <= cx <= (vr - margin) and (vt + margin) <= cy <= (vb - margin)


def notches_toward(bbox: Sequence[int], viewport: Sequence[int], step: int = NOTCHES_PAGE) -> int:
    """Notches (page-down positive) to bring bbox center into viewport."""
    cy = (int(bbox[1]) + int(bbox[3])) // 2
    vt, vb = int(viewport[1]), int(viewport[3])
    mid = (vt + vb) // 2
    if cy > mid:
        return abs(int(step))
    if cy < mid:
        return -abs(int(step))
    return 0
