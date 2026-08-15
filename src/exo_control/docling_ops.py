"""Docling — allowrooted document → markdown (Windows-safe local).

Plain text/json/csv/html work without the package. Tests replace ``_CONVERT``.
"""
from __future__ import annotations

import csv
import json
import re
from io import StringIO
from pathlib import Path
from typing import Any, Dict, Optional

from exo_control.files_ops import _outside_denied, _resolve_under_roots
from exo_control.http_json import truncate
from exo_control.policy import parse_confirm

_CONVERT = None
_BUILTIN = {".txt", ".md", ".markdown", ".json", ".csv", ".html", ".htm", ".xml", ".log"}


def configured() -> bool:
    return True


def _try_docling(path: Path) -> Optional[str]:
    try:
        from docling.document_converter import DocumentConverter
    except Exception:
        return None
    result = DocumentConverter().convert(str(path))
    doc = getattr(result, "document", None)
    if doc is None:
        return None
    export = getattr(doc, "export_to_markdown", None)
    if callable(export):
        return str(export())
    return str(doc)


def _html_to_md(text: str) -> str:
    text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", text)
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</p>", "\n\n", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def _csv_to_md(text: str) -> str:
    rows = list(csv.reader(StringIO(text)))[:21]
    if not rows:
        return ""
    widths = [max(len(c) for c in col) for col in zip(*rows)]

    def fmt(row: list) -> str:
        cells = [(row[i] if i < len(row) else "") for i in range(len(widths))]
        return "| " + " | ".join(cells) + " |"

    header = fmt(rows[0])
    sep = "| " + " | ".join("-" * max(3, w) for w in widths) + " |"
    return "\n".join([header, sep, *[fmt(r) for r in rows[1:]]])


def _builtin_convert(path: Path) -> Optional[str]:
    suffix = path.suffix.lower()
    if suffix not in _BUILTIN:
        return None
    raw = path.read_text(encoding="utf-8", errors="replace")
    if suffix in {".txt", ".md", ".markdown", ".log", ".xml"}:
        return raw
    if suffix == ".json":
        try:
            pretty = json.dumps(json.loads(raw), indent=2, ensure_ascii=False)
        except json.JSONDecodeError:
            pretty = raw
        return f"```json\n{pretty}\n```"
    if suffix == ".csv":
        return _csv_to_md(raw)
    if suffix in {".html", ".htm"}:
        return _html_to_md(raw)
    return raw


def convert(step: Dict[str, Any]) -> Dict[str, Any]:
    path = str(step.get("path") or step.get("file") or step.get("src") or "").strip()
    if not path:
        return {"ok": False, "error": "docling requires path", "code": "MISSING_PATH"}
    ok, resolved, outside = _resolve_under_roots(path)
    if not ok:
        return {"ok": False, "error": resolved, "code": "BAD_PATH"}
    if outside:
        denied = _outside_denied("docling", resolved, parse_confirm(step.get("confirm", False)))
        if denied is not None:
            return denied
    p = Path(resolved)
    if not p.exists() or not p.is_file():
        return {"ok": False, "error": f"file not found: {p}", "code": "NOT_FOUND"}
    try:
        if _CONVERT is not None:
            markdown = _CONVERT(p)
        else:
            markdown = _builtin_convert(p)
            if markdown is None:
                markdown = _try_docling(p)
        if markdown is None:
            return {
                "ok": False,
                "error": "docling needs the docling package for this type",
                "code": "MISSING_DEPENDENCY",
                "path": str(p),
                "suffix": p.suffix.lower(),
            }
        verbose = step.get("verbose") is True
        text = str(markdown)
        return {
            "ok": True,
            "provider": "docling",
            "path": str(p),
            "markdown": text if verbose else truncate(text, 8000),
            "chars": len(text),
            "suffix": p.suffix.lower(),
        }
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}", "code": "CONVERT_FAILED"}
