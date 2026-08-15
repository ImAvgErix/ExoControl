"""Local keyword RAG over allowrooted text files. No cloud embeddings."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from exo_control.files_ops import default_roots
from exo_control.http_json import clip_int, truncate

_TEXT = {".txt", ".md", ".markdown", ".csv", ".json", ".html", ".htm", ".log", ".xml", ".rst"}


def configured() -> bool:
    return True


def _terms(query: str) -> List[str]:
    return [t for t in "".join(ch.lower() if ch.isalnum() else " " for ch in query).split() if t]


def _score(text: str, terms: List[str]) -> int:
    low = text.lower()
    return sum(low.count(t) for t in terms)


def search(step: Dict[str, Any]) -> Dict[str, Any]:
    query = str(step.get("query") or step.get("q") or step.get("text") or "").strip()
    if not query:
        return {"ok": False, "error": "rag requires query", "code": "MISSING_QUERY"}
    terms = _terms(query)
    if not terms:
        return {"ok": False, "error": "rag query has no searchable terms", "code": "BAD_QUERY"}
    limit = clip_int(step.get("max") or step.get("limit") or 8, 8, 1, 40)
    hits: List[Dict[str, Any]] = []
    for root in default_roots():
        try:
            root_r = root.resolve()
        except OSError:
            continue
        if not root_r.is_dir():
            continue
        try:
            iterator = root_r.rglob("*")
        except OSError:
            continue
        for entry in iterator:
            try:
                if not entry.is_file() or entry.suffix.lower() not in _TEXT:
                    continue
                if entry.stat().st_size > 400_000:
                    continue
                raw = entry.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for line in raw.splitlines():
                line = line.strip()
                if not line:
                    continue
                sc = _score(line, terms)
                if sc <= 0:
                    continue
                hits.append({"path": str(entry), "text": truncate(line, 240), "score": sc})
    hits.sort(key=lambda h: int(h["score"]), reverse=True)
    hits = hits[:limit]
    return {"ok": True, "provider": "local", "query": query, "hits": hits, "count": len(hits)}
