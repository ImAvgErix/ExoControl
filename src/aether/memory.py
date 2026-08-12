"""
UI Memory — remember successful targets so repeated goals are faster.

Persists across process relaunch under AETHER_STATE_DIR / ui_memory.json.
Keys prefer process name (survives PID recycle) over raw pid.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


def _state_dir() -> Path:
    raw = os.environ.get("AETHER_STATE_DIR") or os.environ.get("AETHER_LOCK_DIR")
    if raw:
        p = Path(raw)
        # if lock dir passed, use sibling state or same
        if p.name == "locks":
            p = p.parent / "state"
        return p
    home = Path(os.environ.get("USERPROFILE") or os.environ.get("HOME") or ".")
    return home / ".aether" / "state"


@dataclass
class MemoryHit:
    query: str
    label: str
    kind: str
    x: Optional[int]
    y: Optional[int]
    bbox: Optional[List[int]]
    pid: Optional[int] = None
    process_name: Optional[str] = None
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

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "MemoryHit":
        return cls(
            query=str(d.get("query") or ""),
            label=str(d.get("label") or ""),
            kind=str(d.get("kind") or "unknown"),
            x=d.get("x"),
            y=d.get("y"),
            bbox=d.get("bbox"),
            pid=d.get("pid"),
            process_name=d.get("process_name"),
            window_id=d.get("window_id"),
            element_index=d.get("element_index"),
            success_count=int(d.get("success_count") or 1),
            fail_count=int(d.get("fail_count") or 0),
            last_success=float(d.get("last_success") or time.time()),
            source=str(d.get("source") or ""),
        )


class UIMemory:
    def __init__(
        self,
        max_entries: int = 200,
        *,
        persist: bool = True,
        path: Optional[Path] = None,
    ):
        self.max_entries = max_entries
        self.persist = persist
        self.path = path or (_state_dir() / "ui_memory.json")
        self._hits: Dict[str, MemoryHit] = {}
        if self.persist:
            self.load()

    def _key(
        self,
        query: str,
        *,
        pid: Optional[int] = None,
        process_name: Optional[str] = None,
    ) -> str:
        q = (query or "").strip().lower()
        proc = (process_name or "").strip().lower()
        if proc:
            return f"{q}|proc={proc}"
        return f"{q}|pid={pid}"

    def _proc_name(self, target: Any = None, pid: Optional[int] = None) -> Optional[str]:
        if target is not None:
            for attr in ("process_name", "exe", "app"):
                v = getattr(target, attr, None)
                if v:
                    return Path(str(v)).stem.lower()
            meta = getattr(target, "meta", None)
            if isinstance(meta, dict) and meta.get("process_name"):
                return Path(str(meta["process_name"])).stem.lower()
            # target may be dict-like
            if isinstance(target, dict):
                for attr in ("process_name", "exe", "app", "name"):
                    if target.get(attr):
                        return Path(str(target[attr])).stem.lower()
                nested = target.get("meta")
                if isinstance(nested, dict) and nested.get("process_name"):
                    return Path(str(nested["process_name"])).stem.lower()
        if pid is None:
            return None
        try:
            import psutil  # type: ignore

            return Path(psutil.Process(int(pid)).name()).stem.lower()
        except Exception:
            return None

    def record_success(self, query: str, target: Any) -> None:
        if not query or target is None:
            return
        pid = getattr(target, "pid", None)
        if pid is None and isinstance(target, dict):
            pid = target.get("pid")
        proc = self._proc_name(target, pid)
        k = self._key(query, pid=pid, process_name=proc)
        if k in self._hits:
            h = self._hits[k]
            h.success_count += 1
            h.fail_count = max(0, h.fail_count - 1)  # recover after hits
            h.last_success = time.time()
            h.label = getattr(target, "label", None) or (
                target.get("label") if isinstance(target, dict) else h.label
            ) or h.label
            h.x = getattr(target, "x", None) if not isinstance(target, dict) else target.get("x", h.x)
            h.y = getattr(target, "y", None) if not isinstance(target, dict) else target.get("y", h.y)
            h.bbox = getattr(target, "bbox", None) if not isinstance(target, dict) else target.get("bbox", h.bbox)
            h.element_index = (
                getattr(target, "element_index", None)
                if not isinstance(target, dict)
                else target.get("element_index", h.element_index)
            )
            h.window_id = (
                getattr(target, "window_id", None)
                if not isinstance(target, dict)
                else target.get("window_id", h.window_id)
            )
            h.process_name = proc or h.process_name
            h.pid = pid if pid is not None else h.pid
        else:
            if isinstance(target, dict):
                self._hits[k] = MemoryHit(
                    query=query.strip().lower(),
                    label=str(target.get("label") or query),
                    kind=str(target.get("kind") or "unknown"),
                    x=target.get("x"),
                    y=target.get("y"),
                    bbox=target.get("bbox"),
                    pid=pid,
                    process_name=proc,
                    window_id=target.get("window_id"),
                    element_index=target.get("element_index"),
                    source=str(target.get("source") or ""),
                )
            else:
                self._hits[k] = MemoryHit(
                    query=query.strip().lower(),
                    label=getattr(target, "label", query),
                    kind=getattr(target, "kind", "unknown"),
                    x=getattr(target, "x", None),
                    y=getattr(target, "y", None),
                    bbox=getattr(target, "bbox", None),
                    pid=pid,
                    process_name=proc,
                    window_id=getattr(target, "window_id", None),
                    element_index=getattr(target, "element_index", None),
                    source=getattr(target, "source", "") or "",
                )
        self._trim()
        self.save()

    def record_failure(self, query: str, pid: Optional[int] = None, process_name: Optional[str] = None) -> None:
        proc = process_name or self._proc_name(pid=pid)
        k = self._key(query, pid=pid, process_name=proc)
        if k in self._hits:
            self._hits[k].fail_count += 1
            # invalidate soft: high fail rate drops score; hard-drop if hopeless
            if self._hits[k].fail_count >= 3 and self._hits[k].success_count <= 1:
                self._hits.pop(k, None)
            self.save()
            return
        # also fail fuzzy matches for same query
        q = (query or "").strip().lower()
        changed = False
        for key, h in list(self._hits.items()):
            if h.query == q:
                h.fail_count += 1
                if h.fail_count >= 3 and h.success_count <= 1:
                    self._hits.pop(key, None)
                changed = True
        if changed:
            self.save()

    def invalidate(self, query: str) -> int:
        q = (query or "").strip().lower()
        removed = 0
        for key in list(self._hits.keys()):
            if self._hits[key].query == q or key.startswith(q + "|"):
                self._hits.pop(key, None)
                removed += 1
        if removed:
            self.save()
        return removed

    def lookup(
        self,
        query: str,
        pid: Optional[int] = None,
        process_name: Optional[str] = None,
    ) -> Optional[MemoryHit]:
        proc = process_name or self._proc_name(pid=pid)
        k = self._key(query, pid=pid, process_name=proc)
        hit = self._hits.get(k)
        if hit and hit.score >= 0.35:
            return hit
        # same query any process
        q = (query or "").strip().lower()
        candidates = [h for h in self._hits.values() if h.query == q or (q and q in h.query)]
        if not candidates:
            return None
        if proc:
            preferred = [h for h in candidates if (h.process_name or "") == proc]
            if preferred:
                candidates = preferred
        candidates.sort(key=lambda h: h.score, reverse=True)
        return candidates[0] if candidates[0].score >= 0.35 else None

    def stats(self) -> Dict[str, Any]:
        return {
            "entries": len(self._hits),
            "persist": self.persist,
            "path": str(self.path),
            "top": [
                {
                    "query": h.query,
                    "label": h.label,
                    "score": round(h.score, 2),
                    "success": h.success_count,
                    "fail": h.fail_count,
                    "process": h.process_name,
                }
                for h in sorted(self._hits.values(), key=lambda x: x.score, reverse=True)[:8]
            ],
        }

    def _trim(self) -> None:
        while len(self._hits) > self.max_entries:
            worst = min(self._hits.items(), key=lambda kv: kv[1].score)
            self._hits.pop(worst[0], None)

    def save(self) -> None:
        if not self.persist:
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "version": 1,
                "saved_at": time.time(),
                "hits": {k: v.to_dict() for k, v in self._hits.items()},
            }
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(payload), encoding="utf-8")
            tmp.replace(self.path)
        except Exception:
            pass

    def load(self) -> None:
        if not self.persist or not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            hits = data.get("hits") or {}
            self._hits = {
                str(k): MemoryHit.from_dict(v)
                for k, v in hits.items()
                if isinstance(v, dict)
            }
        except Exception:
            self._hits = {}
