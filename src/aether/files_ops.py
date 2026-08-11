"""Allowrooted file ops for Jarvis OS."""
from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple


def default_roots() -> List[Path]:
    roots: List[Path] = []
    home = Path(os.environ.get("USERPROFILE") or Path.home())
    roots.append((home / ".aether" / "workspace").resolve())
    extra = os.environ.get("AETHER_FILE_ROOTS") or ""
    if extra.strip():
        for part in extra.split(os.pathsep):
            part = part.strip()
            if not part:
                continue
            try:
                roots.append(Path(part).expanduser().resolve())
            except OSError:
                continue
    return roots


def _audit_path() -> Path:
    state = os.environ.get("AETHER_STATE_DIR")
    if state:
        base = Path(state)
    else:
        home = Path(os.environ.get("USERPROFILE") or Path.home())
        base = home / ".aether" / "state"
    base.mkdir(parents=True, exist_ok=True)
    return base / "files_audit.jsonl"


def audit_append(event: Dict[str, Any]) -> None:
    try:
        payload = dict(event)
        payload.setdefault("ts", time.time())
        with open(_audit_path(), "a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")
    except Exception:
        pass


def _resolve_under_roots(
    path: str,
    roots: Optional[Sequence[Path]] = None,
) -> Tuple[bool, str, bool]:
    """Return (ok, resolved_path|error, outside).

    ok means the path string resolved; outside means not under any allowroot.
    """
    roots = list(roots) if roots is not None else default_roots()
    try:
        resolved = Path(path).expanduser().resolve()
    except Exception as exc:
        return False, f"invalid path: {exc}", True
    outside = True
    for root in roots:
        try:
            root_r = root.resolve()
        except OSError:
            continue
        try:
            resolved.relative_to(root_r)
            outside = False
            break
        except ValueError:
            continue
    return True, str(resolved), outside


def files_list(
    path: str = ".",
    max_items: int = 200,
    *,
    confirm: bool = False,
    roots: Optional[Sequence[Path]] = None,
) -> Dict[str, Any]:
    ok, resolved_or_err, outside = _resolve_under_roots(path, roots)
    if not ok:
        return {"ok": False, "error": resolved_or_err}
    if outside and not confirm:
        audit_append({"op": "files_list", "path": resolved_or_err, "denied": "outside_root", "confirm": False})
        return {"ok": False, "error": "path outside allowroots; pass confirm=true", "path": resolved_or_err, "outside": True}
    root = Path(resolved_or_err)
    if not root.exists():
        return {"ok": False, "error": f"path not found: {root}"}
    if not root.is_dir():
        return {"ok": False, "error": f"not a directory: {root}"}
    items: List[Dict[str, Any]] = []
    try:
        for entry in root.iterdir():
            try:
                st = entry.stat()
                items.append({
                    "name": entry.name,
                    "path": str(entry),
                    "is_dir": entry.is_dir(),
                    "size": int(st.st_size) if entry.is_file() else None,
                })
            except OSError:
                continue
            if len(items) >= max_items:
                break
        items.sort(key=lambda x: (not x["is_dir"], x["name"].lower()))
        return {
            "ok": True,
            "path": str(root),
            "entries": items,
            "count": len(items),
            "capped": len(items) >= max_items,
            "outside": outside,
        }
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def files_read(
    path: str,
    max_bytes: int = 32_000,
    *,
    confirm: bool = False,
    roots: Optional[Sequence[Path]] = None,
) -> Dict[str, Any]:
    ok, resolved_or_err, outside = _resolve_under_roots(path, roots)
    if not ok:
        return {"ok": False, "error": resolved_or_err}
    if outside and not confirm:
        audit_append({"op": "files_read", "path": resolved_or_err, "denied": "outside_root", "confirm": False})
        return {"ok": False, "error": "path outside allowroots; pass confirm=true", "path": resolved_or_err, "outside": True}
    p = Path(resolved_or_err)
    if not p.exists() or not p.is_file():
        return {"ok": False, "error": f"file not found: {p}"}
    try:
        data = p.read_bytes()[: max(0, int(max_bytes))]
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            text = data.decode("utf-8", errors="replace")
        return {
            "ok": True,
            "path": str(p),
            "text": text,
            "bytes": len(data),
            "truncated": p.stat().st_size > len(data),
            "outside": outside,
        }
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def files_write(
    path: str,
    text: str = "",
    *,
    confirm: bool = False,
    roots: Optional[Sequence[Path]] = None,
) -> Dict[str, Any]:
    ok, resolved_or_err, outside = _resolve_under_roots(path, roots)
    if not ok:
        return {"ok": False, "error": resolved_or_err}
    if outside and not confirm:
        audit_append({"op": "files_write", "path": resolved_or_err, "denied": "outside_root", "confirm": False})
        return {"ok": False, "error": "path outside allowroots; pass confirm=true", "path": resolved_or_err, "outside": True}
    p = Path(resolved_or_err)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(str(text), encoding="utf-8")
        if outside:
            audit_append({"op": "files_write", "path": str(p), "confirm": True, "outside": True})
        return {"ok": True, "path": str(p), "bytes": len(str(text).encode("utf-8")), "outside": outside}
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def files_copy(
    src: str,
    dst: str,
    *,
    confirm: bool = False,
    roots: Optional[Sequence[Path]] = None,
) -> Dict[str, Any]:
    ok_s, src_r, out_s = _resolve_under_roots(src, roots)
    ok_d, dst_r, out_d = _resolve_under_roots(dst, roots)
    if not ok_s:
        return {"ok": False, "error": src_r}
    if not ok_d:
        return {"ok": False, "error": dst_r}
    if (out_s or out_d) and not confirm:
        audit_append({"op": "files_copy", "src": src_r, "dst": dst_r, "denied": "outside_root", "confirm": False})
        return {"ok": False, "error": "path outside allowroots; pass confirm=true", "outside": True}
    try:
        Path(dst_r).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_r, dst_r)
        if out_s or out_d:
            audit_append({"op": "files_copy", "src": src_r, "dst": dst_r, "confirm": True, "outside": True})
        return {"ok": True, "src": src_r, "dst": dst_r}
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def files_move(
    src: str,
    dst: str,
    *,
    confirm: bool = False,
    roots: Optional[Sequence[Path]] = None,
) -> Dict[str, Any]:
    ok_s, src_r, out_s = _resolve_under_roots(src, roots)
    ok_d, dst_r, out_d = _resolve_under_roots(dst, roots)
    if not ok_s:
        return {"ok": False, "error": src_r}
    if not ok_d:
        return {"ok": False, "error": dst_r}
    if (out_s or out_d) and not confirm:
        audit_append({"op": "files_move", "src": src_r, "dst": dst_r, "denied": "outside_root", "confirm": False})
        return {"ok": False, "error": "path outside allowroots; pass confirm=true", "outside": True}
    try:
        Path(dst_r).parent.mkdir(parents=True, exist_ok=True)
        shutil.move(src_r, dst_r)
        audit_append({"op": "files_move", "src": src_r, "dst": dst_r, "confirm": bool(confirm), "outside": out_s or out_d})
        return {"ok": True, "src": src_r, "dst": dst_r}
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def files_delete(
    path: str,
    *,
    confirm: bool = False,
    recursive: bool = False,
    roots: Optional[Sequence[Path]] = None,
) -> Dict[str, Any]:
    ok, resolved_or_err, outside = _resolve_under_roots(path, roots)
    if not ok:
        return {"ok": False, "error": resolved_or_err}
    if outside and not confirm:
        audit_append({"op": "files_delete", "path": resolved_or_err, "denied": "outside_root", "confirm": False})
        return {"ok": False, "error": "path outside allowroots; pass confirm=true", "path": resolved_or_err, "outside": True}
    p = Path(resolved_or_err)
    if not p.exists():
        return {"ok": False, "error": f"path not found: {p}"}
    try:
        if p.is_dir():
            # non-empty / recursive
            try:
                next(p.iterdir())
                non_empty = True
            except StopIteration:
                non_empty = False
            if non_empty or recursive:
                if not confirm:
                    audit_append({
                        "op": "files_delete",
                        "path": str(p),
                        "denied": "recursive_delete_needs_confirm",
                        "confirm": False,
                        "recursive": True,
                    })
                    return {
                        "ok": False,
                        "error": "recursive delete requires confirm=true",
                        "path": str(p),
                        "audit": True,
                    }
                shutil.rmtree(str(p))
                audit_append({"op": "files_delete", "path": str(p), "confirm": True, "recursive": True})
                return {"ok": True, "path": str(p), "deleted": "dir_recursive"}
            p.rmdir()
            audit_append({"op": "files_delete", "path": str(p), "confirm": bool(confirm), "recursive": False})
            return {"ok": True, "path": str(p), "deleted": "dir_empty"}
        p.unlink()
        audit_append({"op": "files_delete", "path": str(p), "confirm": bool(confirm), "outside": outside})
        return {"ok": True, "path": str(p), "deleted": "file"}
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
