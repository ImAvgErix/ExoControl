"""Allowrooted file extras: zip/unzip, mkdir, stat, tree, diff, sqlite, pdf/image info, b64."""
from __future__ import annotations

import base64
import difflib
import sqlite3
import zipfile
from pathlib import Path
from typing import Any, Dict, List

from exo_control.files_ops import _outside_denied, _resolve_under_roots
from exo_control.http_json import clip_int, truncate
from exo_control.policy import parse_confirm

_WRITE_SQL = ("insert", "update", "delete", "drop", "alter", "create", "replace", "pragma")


def _resolve(op: str, path: str, confirm: Any = False) -> Dict[str, Any]:
    if not path:
        return {"ok": False, "error": f"{op} requires path", "code": "MISSING_PATH"}
    ok, resolved, outside = _resolve_under_roots(path)
    if not ok:
        return {"ok": False, "error": resolved, "code": "BAD_PATH"}
    if outside:
        denied = _outside_denied(op, resolved, parse_confirm(confirm))
        if denied:
            return denied
    return {"ok": True, "path": resolved}


def files_mkdir(step: Dict[str, Any]) -> Dict[str, Any]:
    got = _resolve("files_mkdir", str(step.get("path") or step.get("dir") or ""), step.get("confirm"))
    if not got.get("ok"):
        return got
    Path(got["path"]).mkdir(parents=True, exist_ok=True)
    return {"ok": True, "path": got["path"], "created": True}


_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tif", ".tiff", ".ico"}


def files_stat(step: Dict[str, Any]) -> Dict[str, Any]:
    got = _resolve("files_stat", str(step.get("path") or step.get("file") or ""), step.get("confirm"))
    if not got.get("ok"):
        return got
    p = Path(got["path"])
    if not p.exists():
        return {"ok": False, "error": f"not found: {p}", "code": "NOT_FOUND"}
    st = p.stat()
    suffix = p.suffix.lower()
    out: Dict[str, Any] = {
        "ok": True,
        "path": str(p),
        "is_file": p.is_file(),
        "is_dir": p.is_dir(),
        "size": int(st.st_size),
        "mtime": int(st.st_mtime),
        "suffix": suffix,
    }
    if p.is_file() and (suffix == ".pdf" or step.get("_op") == "pdf_info"):
        out["pdf"] = p.read_bytes()[:16].startswith(b"%PDF")
    if p.is_file() and (suffix in _IMAGE_SUFFIXES or step.get("_op") == "image_info"):
        out["image"] = suffix in _IMAGE_SUFFIXES
    return out


def tree(step: Dict[str, Any]) -> Dict[str, Any]:
    path = str(step.get("path") or step.get("dir") or "").strip()
    got = _resolve("tree", path or ".", step.get("confirm"))
    if not got.get("ok"):
        return got
    root = Path(got["path"])
    if not root.exists():
        return {"ok": False, "error": f"not found: {root}", "code": "NOT_FOUND"}
    limit = clip_int(step.get("max") or 80, 80, 1, 200)
    entries: List[str] = []
    if root.is_file():
        entries.append(root.name)
    else:
        for item in sorted(root.rglob("*")):
            try:
                entries.append(str(item.relative_to(root)))
            except ValueError:
                entries.append(item.name)
            if len(entries) >= limit:
                break
    return {"ok": True, "path": str(root), "entries": entries, "count": len(entries)}


def diff_files(step: Dict[str, Any]) -> Dict[str, Any]:
    a = _resolve("diff_files", str(step.get("a") or step.get("left") or step.get("path") or ""), step.get("confirm"))
    b = _resolve("diff_files", str(step.get("b") or step.get("right") or step.get("dest") or ""), step.get("confirm"))
    if not a.get("ok"):
        return a
    if not b.get("ok"):
        return b
    left = Path(a["path"]).read_text(encoding="utf-8", errors="replace").splitlines()
    right = Path(b["path"]).read_text(encoding="utf-8", errors="replace").splitlines()
    lines = list(difflib.unified_diff(left, right, fromfile=a["path"], tofile=b["path"], lineterm=""))
    return {
        "ok": True,
        "changed": bool(lines),
        "diff": truncate("\n".join(lines), 4000),
        "a": a["path"],
        "b": b["path"],
    }


def zip_files(step: Dict[str, Any]) -> Dict[str, Any]:
    src = _resolve("zip", str(step.get("path") or step.get("src") or ""), step.get("confirm"))
    dest = _resolve("zip", str(step.get("dest") or step.get("out") or ""), step.get("confirm"))
    if not src.get("ok"):
        return src
    if not dest.get("ok"):
        return dest
    source = Path(src["path"])
    out = Path(dest["path"])
    if out.suffix.lower() != ".zip":
        out = out.with_suffix(".zip")
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        if source.is_file():
            zf.write(source, arcname=source.name)
        else:
            for item in source.rglob("*"):
                if item.is_file():
                    zf.write(item, arcname=str(item.relative_to(source)))
    return {"ok": True, "path": str(out), "src": str(source)}


def unzip_files(step: Dict[str, Any]) -> Dict[str, Any]:
    if not parse_confirm(step.get("confirm", False)):
        return {"ok": False, "error": "unzip requires confirm=true", "code": "CONFIRM_REQUIRED"}
    src = _resolve("unzip", str(step.get("path") or step.get("src") or ""), True)
    dest_raw = str(step.get("dest") or step.get("out") or "")
    dest = _resolve("unzip", dest_raw, True) if dest_raw else src
    if not src.get("ok"):
        return src
    if dest_raw and not dest.get("ok"):
        return dest
    archive = Path(src["path"])
    target = Path(dest["path"]) if dest_raw else archive.with_suffix("")
    target.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive, "r") as zf:
        zf.extractall(target)
        names = zf.namelist()[:40]
    return {"ok": True, "path": str(target), "files": names, "count": len(names)}


def sqlite(step: Dict[str, Any]) -> Dict[str, Any]:
    got = _resolve("sqlite", str(step.get("path") or step.get("db") or ""), step.get("confirm"))
    if not got.get("ok"):
        return got
    sql = str(step.get("sql") or step.get("query") or "").strip()
    if not sql:
        return {"ok": False, "error": "sqlite requires sql", "code": "MISSING_SQL"}
    head = sql.lstrip().split(None, 1)[0].lower() if sql.split() else ""
    mutating = head in _WRITE_SQL or any(tok in sql.lower() for tok in (" insert ", " update ", " delete "))
    if mutating and not parse_confirm(step.get("confirm", False)):
        return {"ok": False, "error": "sqlite write requires confirm=true", "code": "CONFIRM_REQUIRED"}
    try:
        conn = sqlite3.connect(got["path"])
        try:
            cur = conn.execute(sql)
            if mutating:
                conn.commit()
                return {"ok": True, "path": got["path"], "rowcount": cur.rowcount}
            rows = cur.fetchmany(clip_int(step.get("max") or 50, 50, 1, 200))
            cols = [d[0] for d in (cur.description or [])]
            return {"ok": True, "path": got["path"], "columns": cols, "rows": [list(r) for r in rows], "count": len(rows)}
        finally:
            conn.close()
    except sqlite3.Error as exc:
        return {"ok": False, "error": str(exc), "code": "SQLITE_ERROR"}


def pdf_info(step: Dict[str, Any]) -> Dict[str, Any]:
    payload = dict(step)
    payload["_op"] = "pdf_info"
    out = files_stat(payload)
    if out.get("ok") and not out.get("is_file"):
        return {"ok": False, "error": f"not found: {out.get('path')}", "code": "NOT_FOUND"}
    return out


def image_info(step: Dict[str, Any]) -> Dict[str, Any]:
    payload = dict(step)
    payload["_op"] = "image_info"
    out = files_stat(payload)
    if out.get("ok") and not out.get("is_file"):
        return {"ok": False, "error": f"not found: {out.get('path')}", "code": "NOT_FOUND"}
    return out


def b64(step: Dict[str, Any]) -> Dict[str, Any]:
    got = _resolve("b64", str(step.get("path") or step.get("file") or ""), step.get("confirm"))
    if not got.get("ok"):
        return got
    p = Path(got["path"])
    if not p.is_file():
        return {"ok": False, "error": f"not found: {p}", "code": "NOT_FOUND"}
    action = str(step.get("action") or "encode").lower()
    data = p.read_bytes()
    if action == "decode":
        try:
            raw = base64.b64decode(data)
        except Exception as exc:
            return {"ok": False, "error": str(exc), "code": "B64_ERROR"}
        return {"ok": True, "action": "decode", "bytes": len(raw)}
    encoded = base64.b64encode(data).decode("ascii")
    return {"ok": True, "action": "encode", "b64": truncate(encoded, 4000), "bytes": len(data)}
