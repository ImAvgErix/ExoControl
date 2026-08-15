"""Windows desk extras — volume, winget, recycle, event log, OCR, STT, TTS.

Linux CI uses ``_IMPL`` hooks. Native paths are Windows-only and fail closed.
``volume`` set and ``recycle`` empty need ``confirm=true``.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from typing import Any, Callable, Dict, List, Optional

from exo_control.files_ops import _outside_denied, _resolve_under_roots
from exo_control.http_json import clip_int, truncate
from exo_control.policy import parse_confirm

_IMPL: Optional[Callable[[str, Dict[str, Any]], Optional[Dict[str, Any]]]] = None


def _windows_only(op: str) -> Dict[str, Any]:
    return {
        "ok": False,
        "error": f"{op} is Windows-only",
        "code": "WINDOWS_ONLY",
    }


def _hook(op: str, step: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if _IMPL is None:
        return None
    return _IMPL(op, step)


def _run(args: List[str], timeout: float = 25.0) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False)


def volume(step: Dict[str, Any]) -> Dict[str, Any]:
    action = str(step.get("action") or "").lower()
    wants_set = (
        step.get("level") is not None
        or step.get("mute") is not None
        or action in {"set", "mute", "unmute"}
    )
    if wants_set and not parse_confirm(step.get("confirm", False)):
        return {"ok": False, "error": "volume set requires confirm=true", "code": "CONFIRM_REQUIRED"}
    hooked = _hook("volume", step)
    if hooked is not None:
        return hooked
    if sys.platform != "win32":
        return _windows_only("volume")
    return {"ok": False, "error": "volume native backend unavailable", "code": "UNAVAILABLE"}


def winget(step: Dict[str, Any]) -> Dict[str, Any]:
    hooked = _hook("winget", step)
    if hooked is not None:
        return hooked
    if sys.platform != "win32":
        return _windows_only("winget")
    exe = shutil.which("winget")
    if not exe:
        return {"ok": False, "error": "winget not on PATH", "code": "UNAVAILABLE"}
    query = str(step.get("query") or step.get("q") or step.get("name") or "").strip()
    action = str(step.get("action") or ("search" if query else "list")).lower()
    if action not in {"search", "list", "show"}:
        action = "search" if query else "list"
    args = [exe, action]
    if query:
        args.append(query)
    args.extend(["--disable-interactivity", "--accept-source-agreements"])
    try:
        proc = _run(args)
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return {"ok": False, "error": str(exc), "code": "UNAVAILABLE"}
    return {
        "ok": proc.returncode == 0,
        "action": action,
        "stdout": truncate((proc.stdout or "").strip(), 4000),
        "error": None if proc.returncode == 0 else truncate((proc.stderr or "winget failed").strip(), 400),
        "code": None if proc.returncode == 0 else "WINGET_ERROR",
    }


def recycle(step: Dict[str, Any]) -> Dict[str, Any]:
    action = str(step.get("action") or "list").lower()
    if action in {"empty", "clear", "wipe"} and not parse_confirm(step.get("confirm", False)):
        return {"ok": False, "error": "recycle empty requires confirm=true", "code": "CONFIRM_REQUIRED"}
    hooked = _hook("recycle", step)
    if hooked is not None:
        return hooked
    if sys.platform != "win32":
        return _windows_only("recycle")
    return {"ok": False, "error": "recycle native backend unavailable", "code": "UNAVAILABLE"}


def eventlog(step: Dict[str, Any]) -> Dict[str, Any]:
    hooked = _hook("eventlog", step)
    if hooked is not None:
        return hooked
    if sys.platform != "win32":
        return _windows_only("eventlog")
    log = str(step.get("log") or step.get("name") or "Application")
    count = clip_int(step.get("max") or step.get("limit") or 12, 12, 1, 40)
    exe = shutil.which("wevtutil") or "wevtutil"
    try:
        proc = _run([exe, "qe", log, f"/c:{count}", "/rd:true", "/f:text"])
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return {"ok": False, "error": str(exc), "code": "UNAVAILABLE"}
    if proc.returncode != 0:
        return {
            "ok": False,
            "error": truncate((proc.stderr or "wevtutil failed").strip(), 400),
            "code": "EVENTLOG_ERROR",
        }
    return {
        "ok": True,
        "log": log,
        "text": truncate((proc.stdout or "").strip(), 4000),
    }


def ocr_win(step: Dict[str, Any]) -> Dict[str, Any]:
    hooked = _hook("ocr_win", step)
    if hooked is not None:
        return hooked
    path = str(step.get("path") or step.get("image") or "").strip()
    if path:
        ok, resolved, outside = _resolve_under_roots(path)
        if not ok:
            return {"ok": False, "error": resolved, "code": "BAD_PATH"}
        denied = _outside_denied("ocr_win", resolved, parse_confirm(step.get("confirm", False))) if outside else None
        if denied:
            return denied
    if sys.platform != "win32":
        return _windows_only("ocr_win")
    return {"ok": False, "error": "WinRT OCR backend unavailable", "code": "UNAVAILABLE"}


def stt(step: Dict[str, Any]) -> Dict[str, Any]:
    hooked = _hook("stt", step)
    if hooked is not None:
        return hooked
    if sys.platform != "win32":
        return _windows_only("stt")
    return {"ok": False, "error": "Windows Speech backend unavailable", "code": "UNAVAILABLE"}


def tts(step: Dict[str, Any]) -> Dict[str, Any]:
    hooked = _hook("tts", step)
    if hooked is not None:
        return hooked
    text = str(step.get("text") or step.get("say") or step.get("speech") or "")
    if not text.strip():
        return {"ok": False, "error": "tts requires text", "code": "MISSING_TEXT"}
    if sys.platform != "win32":
        return _windows_only("tts")
    return {"ok": False, "error": "SAPI TTS backend unavailable", "code": "UNAVAILABLE"}
