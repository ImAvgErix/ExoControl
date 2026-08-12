"""Compact-by-default payload shaping for Exo Control eyes/snapshot ops."""
from __future__ import annotations

import json
from typing import Any, Dict, List

MAX_COMPACT_CHARS = 4000
MAX_COMPACT_REFS = 40

_STRIP_KEYS = frozenset({
    "screenshot_base64",
    "annotated_screenshot_base64",
    "raw_html",
    "html",
})

_TEXT_KEYS = frozenset({"text_sample", "text", "body"})
_LIST_KEYS = frozenset({
    "elements", "refs", "a11y", "a11y_labels", "ocr", "entries",
    "values", "procs", "services", "tasks", "items",
})


def _json_chars(obj: Any) -> int:
    try:
        return len(json.dumps(obj, ensure_ascii=False, default=str))
    except Exception:
        return len(str(obj))


def _is_huge_blob(value: Any) -> bool:
    if isinstance(value, (bytes, bytearray)):
        return len(value) > 2048
    if isinstance(value, str) and len(value) > 8000 and (
        value.startswith("iVBOR") or value.startswith("/9j/") or value.startswith("data:image")
    ):
        return True
    return False


def _truncate_str(s: str, limit: int) -> str:
    if limit <= 0:
        return ""
    if len(s) <= limit:
        return s
    if limit <= 3:
        return s[:limit]
    return s[: limit - 3] + "..."


def _walk_strip(obj: Any, *, max_refs: int, depth: int = 0) -> Any:
    if depth > 12:
        return None
    if isinstance(obj, dict):
        out: Dict[str, Any] = {}
        for k, v in obj.items():
            if k in _STRIP_KEYS:
                continue
            if _is_huge_blob(v):
                out[k] = "<blob omitted>"
                continue
            if k in _TEXT_KEYS and isinstance(v, str):
                out[k] = _truncate_str(v, 800)
                continue
            if k in _LIST_KEYS and isinstance(v, (list, tuple)):
                capped = list(v)[:max_refs]
                out[k] = [_walk_strip(x, max_refs=max_refs, depth=depth + 1) for x in capped]
                if len(v) > max_refs:
                    out[f"_{k}_capped"] = True
                    out[f"_{k}_total"] = len(v)
                continue
            out[k] = _walk_strip(v, max_refs=max_refs, depth=depth + 1)
        return out
    if isinstance(obj, list):
        capped = obj[:max_refs]
        return [_walk_strip(x, max_refs=max_refs, depth=depth + 1) for x in capped]
    if isinstance(obj, str) and len(obj) > 2000:
        return _truncate_str(obj, 2000)
    if _is_huge_blob(obj):
        return "<blob omitted>"
    return obj


def compact_payload(
    obj: Any,
    *,
    verbose: bool = False,
    max_chars: int = MAX_COMPACT_CHARS,
    max_refs: int = MAX_COMPACT_REFS,
) -> Any:
    """Return a token-efficient view of *obj*.

    When ``verbose`` is True the object is returned mostly unchanged, but absurd
    binary / giant base64 blobs are still dropped.
    """
    if obj is None:
        return obj
    if not isinstance(obj, (dict, list)):
        if verbose:
            return obj
        if isinstance(obj, str) and len(obj) > max_chars:
            return _truncate_str(obj, max_chars)
        return obj

    if verbose:
        if isinstance(obj, dict):
            cleaned = {}
            for k, v in obj.items():
                if k in _STRIP_KEYS or _is_huge_blob(v):
                    continue
                cleaned[k] = v
            return cleaned
        return obj

    shaped = _walk_strip(obj, max_refs=max_refs)
    if not isinstance(shaped, dict):
        shaped = {"value": shaped}

    chars = _json_chars(shaped)
    if chars > max_chars:
        for key in ("text_sample", "text", "body", "raw", "content"):
            if key in shaped and isinstance(shaped[key], str):
                budget = max(32, max_chars - (chars - len(shaped[key])) - 64)
                shaped[key] = _truncate_str(shaped[key], budget)
                chars = _json_chars(shaped)
                if chars <= max_chars:
                    break
        if chars > max_chars:
            for key in list(shaped.keys()):
                if isinstance(shaped.get(key), list) and len(shaped[key]) > 5:
                    shaped[key] = shaped[key][: max(5, max_refs // 4)]
                    shaped[f"_{key}_capped"] = True
            chars = _json_chars(shaped)
        if chars > max_chars:
            for key in ("a11y", "elements", "ocr", "refs", "entries"):
                if key in shaped and chars > max_chars:
                    shaped.pop(key, None)
                    chars = _json_chars(shaped)

    shaped["_compact"] = True
    meta_base = {k: v for k, v in shaped.items() if k != "_chars"}
    shaped["_chars"] = _json_chars(meta_base) + 20
    if shaped["_chars"] > max_chars and isinstance(shaped.get("text_sample"), str):
        over = shaped["_chars"] - max_chars
        shaped["text_sample"] = _truncate_str(
            shaped["text_sample"], max(0, len(shaped["text_sample"]) - over - 10)
        )
        meta_base = {k: v for k, v in shaped.items() if k != "_chars"}
        shaped["_chars"] = _json_chars(meta_base) + 20
    return shaped
