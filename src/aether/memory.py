"""
UI Memory — remember successful targets so repeated goals are faster and more accurate.
"""
from __future__ import annotations
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class MemoryHit:
    query: str
    label: str
    kind: str
    x: Optional[int]
    y: Optional[int]
    bbox: Optional[List[int]]
    pid: Optional[int] = None
    window_id: Optional[int] = None
    element_index: Optional[int] = None
    success_count: int = 1
    fail_count: int = 0
    last_success: float = field(default_factory=time.time)
    source: str = ""

    @property
    def score(self) -> float:
        total = self.success_count + self.fail_count
        rate = self.success_count / max(total, 1)
        recency = max(0.0, 1.0 - (time.time() - self.last_success) / 3600.0)
        return rate * 0.7 + recency * 0.3


class UIMemory:
    def __init__(self, max_entries: int = 200):
        self.max_entries = max_entries
        self._hits: Dict[str, MemoryHit] = {}

    def _key(self, query: str, pid: Optional[int] = None) -> str:
        return f"{(query or '').strip().lower()}|pid={pid}"

    def record_success(self, query: str, target: Any) -> None:
        if not query or target is None:
            return
        pid = getattr(target, "pid", None)
        k = self._key(query, pid)
        if k in self._hits:
            h = self._hits[k]
            h.success_count += 1
            h.last_success = time.time()
            h.label = getattr(target, "label", h.label)
            h.x = getattr(target, "x", h.x)
            h.y = getattr(target, "y", h.y)
            h.bbox = getattr(target, "bbox", h.bbox)
            h.element_index = getattr(target, "element_index", h.element_index)
            h.window_id = getattr(target, "window_id", h.window_id)
        else:
            self._hits[k] = MemoryHit(
                query=query.strip().lower(),
                label=getattr(target, "label", query),
                kind=getattr(target, "kind", "unknown"),
                x=getattr(target, "x", None),
                y=getattr(target, "y", None),
                bbox=getattr(target, "bbox", None),
                pid=pid,
                window_id=getattr(target, "window_id", None),
                element_index=getattr(target, "element_index", None),
                source=getattr(target, "source", ""),
            )
        if len(self._hits) > self.max_entries:
            # drop lowest score
            worst = min(self._hits.items(), key=lambda kv: kv[1].score)
            self._hits.pop(worst[0], None)

    def record_failure(self, query: str, pid: Optional[int] = None) -> None:
        k = self._key(query, pid)
        if k in self._hits:
            self._hits[k].fail_count += 1

    def lookup(self, query: str, pid: Optional[int] = None) -> Optional[MemoryHit]:
        k = self._key(query, pid)
        hit = self._hits.get(k)
        if hit and hit.score >= 0.35:
            return hit
        # fuzzy: any key starting with query
        q = (query or "").strip().lower()
        candidates = [h for key, h in self._hits.items() if q and q in key]
        if not candidates:
            return None
        candidates.sort(key=lambda h: h.score, reverse=True)
        return candidates[0] if candidates[0].score >= 0.35 else None

    def stats(self) -> Dict[str, Any]:
        return {
            "entries": len(self._hits),
            "top": [
                {"query": h.query, "label": h.label, "score": round(h.score, 2),
                 "success": h.success_count, "fail": h.fail_count}
                for h in sorted(self._hits.values(), key=lambda x: x.score, reverse=True)[:8]
            ],
        }
