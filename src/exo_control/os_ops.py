"""High-value OS primitives that make the machine feel fully owned.

Window geometry lives on SmartController; this module covers files extras,
drives, which, and compact os_info.
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence


def os_info() -> Dict[str, Any]:
    from exo_control.trust import snapshot_for_identity

    user = os.environ.get("USERNAME") or os.environ.get("USER") or ""
    out: Dict[str, Any] = {
        "ok": True,
        "hostname": os.environ.get("COMPUTERNAME") or os.environ.get("HOSTNAME") or "",
        "user": user,
        "os": os.name,
        "platform": sys.platform,
        "python": sys.version.split()[0],
        "home": str(Path.home()),
        "cwd": os.getcwd(),
        "trust": snapshot_for_identity(),
    }
    if sys.platform == "win32":
        out["windows"] = os.environ.get("OS") or "Windows"
        out["windir"] = os.environ.get("WINDIR")
    try:
        from exo_control.monitors import list_monitor_dicts

        mons = list_monitor_dicts()
        out["monitors"] = len(mons)
    except Exception:
        out["monitors"] = None
    return out


def drives(max_items: int = 16) -> Dict[str, Any]:
    items: List[Dict[str, Any]] = []
    if os.name == "nt":
        import string

        for letter in string.ascii_uppercase:
            root = Path(f"{letter}:/")
            try:
                if not root.exists():
                    continue
                usage = shutil.disk_usage(str(root))
                items.append({
                    "path": f"{letter}:\\",
                    "total": int(usage.total),
                    "free": int(usage.free),
                })
            except OSError:
                continue
            if len(items) >= max_items:
                break
    else:
        try:
            usage = shutil.disk_usage("/")
            items.append({"path": "/", "total": int(usage.total), "free": int(usage.free)})
        except OSError:
            pass
    return {"ok": True, "drives": items, "count": len(items)}


def which(name: str) -> Dict[str, Any]:
    name = str(name or "").strip()
    if not name:
        return {"ok": False, "error": "which requires name"}
    hit = shutil.which(name)
    if not hit:
        return {"ok": False, "error": "not found", "name": name}
    return {"ok": True, "name": name, "path": hit}


def files_exists(path: str, *, confirm: bool = False, roots: Optional[Sequence[Path]] = None) -> Dict[str, Any]:
    from exo_control import files_ops

    ok, resolved, outside = files_ops._resolve_under_roots(path, roots)
    if not ok:
        return {"ok": False, "error": resolved}
    if outside:
        denied = files_ops._outside_denied("files_exists", resolved, confirm)
        if denied is not None:
            return denied
    p = Path(resolved)
    return {
        "ok": True,
        "path": str(p),
        "exists": p.exists(),
        "is_file": p.is_file() if p.exists() else False,
        "is_dir": p.is_dir() if p.exists() else False,
        "outside": outside,
    }


def files_stat(path: str, *, confirm: bool = False, roots: Optional[Sequence[Path]] = None) -> Dict[str, Any]:
    from exo_control import files_ops

    ok, resolved, outside = files_ops._resolve_under_roots(path, roots)
    if not ok:
        return {"ok": False, "error": resolved}
    if outside:
        denied = files_ops._outside_denied("files_stat", resolved, confirm)
        if denied is not None:
            return denied
    p = Path(resolved)
    if not p.exists():
        return {"ok": False, "error": f"path not found: {p}"}
    try:
        st = p.stat()
        return {
            "ok": True,
            "path": str(p),
            "is_dir": p.is_dir(),
            "is_file": p.is_file(),
            "size": int(st.st_size),
            "mtime": float(st.st_mtime),
            "outside": outside,
        }
    except OSError as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def files_mkdir(
    path: str,
    *,
    confirm: bool = False,
    roots: Optional[Sequence[Path]] = None,
) -> Dict[str, Any]:
    from exo_control import files_ops
    from exo_control.trust import is_protected_system_path

    ok, resolved, outside = files_ops._resolve_under_roots(path, roots)
    if not ok:
        return {"ok": False, "error": resolved}
    if is_protected_system_path(resolved):
        files_ops.audit_append({"op": "files_mkdir", "path": resolved, "denied": "system_path"})
        return {"ok": False, "error": "protected_system_path", "path": resolved, "denied": True}
    if outside:
        denied = files_ops._outside_denied("files_mkdir", resolved, confirm)
        if denied is not None:
            return denied
    p = Path(resolved)
    try:
        p.mkdir(parents=True, exist_ok=True)
        return {"ok": True, "path": str(p), "created": True, "outside": outside}
    except OSError as exc:
        from exo_control.elevate import retry_if_needed

        return retry_if_needed(
            "files_mkdir",
            {"ok": False, "error": f"{type(exc).__name__}: {exc}", "path": str(p)},
            {"path": str(p)},
        )


def files_search(
    path: str = ".",
    pattern: str = "*",
    *,
    max_items: int = 80,
    confirm: bool = False,
    roots: Optional[Sequence[Path]] = None,
) -> Dict[str, Any]:
    from exo_control import files_ops

    ok, resolved, outside = files_ops._resolve_under_roots(path, roots)
    if not ok:
        return {"ok": False, "error": resolved}
    if outside:
        denied = files_ops._outside_denied("files_search", resolved, confirm)
        if denied is not None:
            return denied
    root = Path(resolved)
    if not root.exists() or not root.is_dir():
        return {"ok": False, "error": f"not a directory: {root}"}
    pat = str(pattern or "*").strip() or "*"
    # Refuse unbounded recursive ** from filesystem root even in full trust.
    if pat.startswith("**") and root.anchor and root == Path(root.anchor):
        return {"ok": False, "error": "refusing ** search at drive root"}
    hits: List[Dict[str, Any]] = []
    try:
        iterator = root.rglob(pat[3:] if pat.startswith("**/") else pat) if "**" in pat else root.glob(pat)
        for entry in iterator:
            try:
                hits.append({
                    "name": entry.name,
                    "path": str(entry),
                    "is_dir": entry.is_dir(),
                })
            except OSError:
                continue
            if len(hits) >= max_items:
                break
        return {
            "ok": True,
            "path": str(root),
            "pattern": pat,
            "entries": hits,
            "count": len(hits),
            "capped": len(hits) >= max_items,
        }
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def proc_info(pid: Optional[int] = None, name: Optional[str] = None) -> Dict[str, Any]:
    from exo_control import infra_ops

    if pid is not None:
        try:
            pid_i = int(pid)
        except (TypeError, ValueError):
            return {"ok": False, "error": "invalid pid"}
        pname = infra_ops._proc_name_for_pid(pid_i)
        if not pname:
            return {"ok": False, "error": "unresolved_process", "pid": pid_i}
        return {
            "ok": True,
            "pid": pid_i,
            "name": pname,
            "protected": infra_ops.is_protected_process(pname),
        }
    name_s = (name or "").strip()
    if not name_s:
        return {"ok": False, "error": "proc_info requires pid or name"}
    hits = infra_ops.find_pids_by_name(name_s, max_hits=12)
    return {"ok": True, "name": name_s, "matches": hits, "count": len(hits)}
