"""Windows sys extras plus cross-platform hash / whoami / disk.

Windows-only ops use ``_IMPL`` hooks so Linux CI stays green.
``print``, ``dialog``, power sleep, and ``lnk`` create need ``confirm=true``.
"""
from __future__ import annotations

import getpass
import hashlib
import platform
import shutil
import sys
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from exo_control.files_ops import _outside_denied, _resolve_under_roots, default_roots
from exo_control.policy import parse_confirm

_IMPL: Optional[Callable[[str, Dict[str, Any]], Optional[Dict[str, Any]]]] = None


def _hook(op: str, step: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if _IMPL is None:
        return None
    return _IMPL(op, step)


def _windows_only(op: str) -> Dict[str, Any]:
    return {"ok": False, "error": f"{op} is Windows-only", "code": "WINDOWS_ONLY"}


def _resolve_path(op: str, step: Dict[str, Any]) -> Dict[str, Any]:
    path = str(step.get("path") or step.get("file") or "").strip()
    if not path:
        return {"ok": False, "error": f"{op} requires path", "code": "MISSING_PATH"}
    ok, resolved, outside = _resolve_under_roots(path)
    if not ok:
        return {"ok": False, "error": resolved, "code": "BAD_PATH"}
    if outside:
        denied = _outside_denied(op, resolved, parse_confirm(step.get("confirm", False)))
        if denied:
            return denied
    return {"ok": True, "path": resolved}


def winsearch(step: Dict[str, Any]) -> Dict[str, Any]:
    query = str(step.get("query") or step.get("q") or step.get("text") or "").strip()
    if not query:
        return {"ok": False, "error": "winsearch requires query", "code": "MISSING_QUERY"}
    hooked = _hook("winsearch", step)
    if hooked is not None:
        return hooked
    if sys.platform != "win32":
        return _windows_only("winsearch")
    return {"ok": False, "error": "Windows Search backend unavailable", "code": "UNAVAILABLE"}


def print_file(step: Dict[str, Any]) -> Dict[str, Any]:
    if not parse_confirm(step.get("confirm", False)):
        return {"ok": False, "error": "print requires confirm=true", "code": "CONFIRM_REQUIRED"}
    hooked = _hook("print", step)
    if hooked is not None:
        return hooked
    resolved = _resolve_path("print", step)
    if not resolved.get("ok"):
        return resolved
    if sys.platform != "win32":
        return _windows_only("print")
    return {"ok": False, "error": "print backend unavailable", "code": "UNAVAILABLE"}


def wifi(step: Dict[str, Any]) -> Dict[str, Any]:
    hooked = _hook("wifi", step)
    if hooked is not None:
        return hooked
    if sys.platform != "win32":
        return _windows_only("wifi")
    return {"ok": False, "error": "wifi backend unavailable", "code": "UNAVAILABLE"}


def power(step: Dict[str, Any]) -> Dict[str, Any]:
    action = str(step.get("action") or "status").lower()
    if action in {"sleep", "hibernate", "suspend", "shutdown"} and not parse_confirm(step.get("confirm", False)):
        return {"ok": False, "error": f"power {action} requires confirm=true", "code": "CONFIRM_REQUIRED"}
    hooked = _hook("power", step)
    if hooked is not None:
        return hooked
    if sys.platform != "win32":
        return _windows_only("power")
    return {"ok": False, "error": "power backend unavailable", "code": "UNAVAILABLE"}


def disk(step: Dict[str, Any]) -> Dict[str, Any]:
    path = str(step.get("path") or "").strip()
    if path:
        ok, resolved, outside = _resolve_under_roots(path)
        if not ok:
            return {"ok": False, "error": resolved, "code": "BAD_PATH"}
        if outside:
            denied = _outside_denied("disk", resolved, parse_confirm(step.get("confirm", False)))
            if denied:
                return denied
        target = resolved
    else:
        roots = default_roots()
        target = str(roots[0]) if roots else "."
    try:
        usage = shutil.disk_usage(target)
    except OSError as exc:
        return {"ok": False, "error": str(exc), "code": "DISK_ERROR"}
    return {
        "ok": True,
        "path": target,
        "total": int(usage.total),
        "used": int(usage.used),
        "free": int(usage.free),
    }


def whoami(step: Dict[str, Any]) -> Dict[str, Any]:
    user = getpass.getuser()
    host = platform.node()
    return {
        "ok": True,
        "user": user,
        "host": host,
        "system": platform.system(),
        "platform": sys.platform,
    }


def certs(step: Dict[str, Any]) -> Dict[str, Any]:
    hooked = _hook("certs", step)
    if hooked is not None:
        return hooked
    path = str(step.get("path") or "").strip()
    if path:
        resolved = _resolve_path("certs", step)
        if not resolved.get("ok"):
            return resolved
        p = Path(resolved["path"])
        if not p.is_file():
            return {"ok": False, "error": f"cert file not found: {p}", "code": "NOT_FOUND"}
        return {"ok": True, "path": str(p), "bytes": p.stat().st_size, "suffix": p.suffix.lower()}
    if sys.platform != "win32":
        return _windows_only("certs")
    return {"ok": False, "error": "certificate store backend unavailable", "code": "UNAVAILABLE"}


def file_hash(step: Dict[str, Any]) -> Dict[str, Any]:
    resolved = _resolve_path("hash", step)
    if not resolved.get("ok"):
        return resolved
    p = Path(resolved["path"])
    if not p.is_file():
        return {"ok": False, "error": f"file not found: {p}", "code": "NOT_FOUND"}
    algo = str(step.get("algo") or step.get("algorithm") or "sha256").lower()
    if algo not in {"sha256", "sha1", "md5"}:
        return {"ok": False, "error": "hash algo must be sha256|sha1|md5", "code": "BAD_ALGO"}
    h = hashlib.new(algo)
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    digest = h.hexdigest()
    out = {"ok": True, "path": str(p), "algo": algo, algo: digest, "hex": digest}
    if algo == "sha256":
        out["sha256"] = digest
    return out


def lnk(step: Dict[str, Any]) -> Dict[str, Any]:
    target = str(step.get("target") or step.get("dest") or "").strip()
    if target and not parse_confirm(step.get("confirm", False)):
        return {"ok": False, "error": "lnk create requires confirm=true", "code": "CONFIRM_REQUIRED"}
    hooked = _hook("lnk", step)
    if hooked is not None:
        return hooked
    if sys.platform != "win32":
        return _windows_only("lnk")
    return {"ok": False, "error": "shortcut backend unavailable", "code": "UNAVAILABLE"}


def dialog(step: Dict[str, Any]) -> Dict[str, Any]:
    if not parse_confirm(step.get("confirm", False)):
        return {"ok": False, "error": "dialog requires confirm=true", "code": "CONFIRM_REQUIRED"}
    text = str(step.get("text") or step.get("message") or step.get("body") or "").strip()
    if not text:
        return {"ok": False, "error": "dialog requires text", "code": "MISSING_TEXT"}
    hooked = _hook("dialog", step)
    if hooked is not None:
        return hooked
    if sys.platform != "win32":
        return _windows_only("dialog")
    return {"ok": False, "error": "dialog backend unavailable", "code": "UNAVAILABLE"}
