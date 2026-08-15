"""Cross-platform which/now/uuid/ip/dns plus Windows sys hooks."""
from __future__ import annotations

import shutil
import socket
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from exo_control.http_json import clip_int, truncate
from exo_control.policy import parse_confirm

_IMPL: Optional[Callable[[str, Dict[str, Any]], Optional[Dict[str, Any]]]] = None


def _hook(op: str, step: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if _IMPL is None:
        return None
    return _IMPL(op, step)


def _windows_only(op: str) -> Dict[str, Any]:
    return {"ok": False, "error": f"{op} is Windows-only", "code": "WINDOWS_ONLY"}


def which(step: Dict[str, Any]) -> Dict[str, Any]:
    name = str(step.get("name") or step.get("cmd") or step.get("exe") or "").strip()
    if not name:
        return {"ok": False, "error": "which requires name", "code": "MISSING_NAME"}
    path = shutil.which(name)
    if not path:
        return {"ok": False, "error": f"{name} not on PATH", "code": "NOT_FOUND", "name": name}
    return {"ok": True, "name": name, "path": path}


def now(step: Dict[str, Any]) -> Dict[str, Any]:
    dt = datetime.now(timezone.utc)
    return {"ok": True, "iso": dt.isoformat(), "epoch": int(dt.timestamp()), "tz": "UTC"}


def uuid_gen(step: Dict[str, Any]) -> Dict[str, Any]:
    return {"ok": True, "uuid": str(uuid.uuid4())}


def ip_addr(step: Dict[str, Any]) -> Dict[str, Any]:
    host = socket.gethostname()
    addrs: List[str] = []
    try:
        addrs = list({item[4][0] for item in socket.getaddrinfo(host, None)})
    except socket.gaierror:
        addrs = []
    return {"ok": True, "host": host, "addresses": addrs}


def dns(step: Dict[str, Any]) -> Dict[str, Any]:
    host = str(step.get("host") or step.get("name") or step.get("q") or "").strip()
    if not host:
        return {"ok": False, "error": "dns requires host", "code": "MISSING_HOST"}
    try:
        infos = socket.getaddrinfo(host, None)
        addrs = sorted({item[4][0] for item in infos})
    except socket.gaierror as exc:
        return {"ok": False, "error": str(exc), "code": "DNS_ERROR", "host": host}
    return {"ok": True, "host": host, "addresses": addrs}


def ping(step: Dict[str, Any]) -> Dict[str, Any]:
    hooked = _hook("ping", step)
    if hooked is not None:
        return hooked
    host = str(step.get("host") or step.get("target") or "").strip()
    if not host:
        return {"ok": False, "error": "ping requires host", "code": "MISSING_HOST"}
    count = ["-n", "1"] if sys.platform == "win32" else ["-c", "1"]
    try:
        proc = subprocess.run(
            ["ping", *count, host], capture_output=True, text=True, timeout=8, check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return {"ok": False, "error": str(exc), "code": "UNAVAILABLE"}
    return {
        "ok": proc.returncode == 0,
        "host": host,
        "stdout": truncate((proc.stdout or "").strip(), 1200),
        "error": None if proc.returncode == 0 else "ping failed",
    }


def ports(step: Dict[str, Any]) -> Dict[str, Any]:
    hooked = _hook("ports", step)
    if hooked is not None:
        return hooked
    if sys.platform != "win32":
        return _windows_only("ports")
    from exo_control import win_native
    return win_native.ports(step)


def uptime(step: Dict[str, Any]) -> Dict[str, Any]:
    hooked = _hook("uptime", step)
    if hooked is not None:
        return hooked
    if sys.platform == "linux":
        try:
            raw = PathUptime()
            return {"ok": True, "seconds": raw}
        except Exception:
            pass
    if sys.platform != "win32":
        return {"ok": True, "seconds": None, "monotonic": time.monotonic()}
    from exo_control import win_native
    return win_native.uptime(step)


def PathUptime() -> float:
    with open("/proc/uptime", encoding="utf-8") as fh:
        return float(fh.read().split()[0])


def brightness(step: Dict[str, Any]) -> Dict[str, Any]:
    hooked = _hook("brightness", step)
    if hooked is not None:
        return hooked
    if sys.platform != "win32":
        return _windows_only("brightness")
    from exo_control import win_native
    return win_native.brightness(step)


def lock_pc(step: Dict[str, Any]) -> Dict[str, Any]:
    if not parse_confirm(step.get("confirm", False)):
        return {"ok": False, "error": "lock_pc requires confirm=true", "code": "CONFIRM_REQUIRED"}
    hooked = _hook("lock_pc", step)
    if hooked is not None:
        return hooked
    if sys.platform != "win32":
        return _windows_only("lock_pc")
    from exo_control import win_native
    return win_native.lock_pc(step)


def idle(step: Dict[str, Any]) -> Dict[str, Any]:
    hooked = _hook("idle", step)
    if hooked is not None:
        return hooked
    if sys.platform != "win32":
        return _windows_only("idle")
    from exo_control import win_native
    return win_native.idle(step)


def usb(step: Dict[str, Any]) -> Dict[str, Any]:
    hooked = _hook("usb", step)
    if hooked is not None:
        return hooked
    if sys.platform != "win32":
        return _windows_only("usb")
    from exo_control import win_native
    return win_native.usb(step)


def bluetooth(step: Dict[str, Any]) -> Dict[str, Any]:
    hooked = _hook("bluetooth", step)
    if hooked is not None:
        return hooked
    if sys.platform != "win32":
        return _windows_only("bluetooth")
    from exo_control import win_native
    return win_native.bluetooth(step)


def printers(step: Dict[str, Any]) -> Dict[str, Any]:
    hooked = _hook("printers", step)
    if hooked is not None:
        return hooked
    if sys.platform != "win32":
        return _windows_only("printers")
    from exo_control import win_native
    return win_native.printers(step)


def bitlocker(step: Dict[str, Any]) -> Dict[str, Any]:
    hooked = _hook("bitlocker", step)
    if hooked is not None:
        return hooked
    if sys.platform != "win32":
        return _windows_only("bitlocker")
    from exo_control import win_native
    return win_native.bitlocker(step)


def defender(step: Dict[str, Any]) -> Dict[str, Any]:
    hooked = _hook("defender", step)
    if hooked is not None:
        return hooked
    if sys.platform != "win32":
        return _windows_only("defender")
    from exo_control import win_native
    return win_native.defender(step)


def win_updates(step: Dict[str, Any]) -> Dict[str, Any]:
    hooked = _hook("win_updates", step)
    if hooked is not None:
        return hooked
    if sys.platform != "win32":
        return _windows_only("win_updates")
    from exo_control import win_native
    return win_native.win_updates(step)


def fonts(step: Dict[str, Any]) -> Dict[str, Any]:
    hooked = _hook("fonts", step)
    if hooked is not None:
        return hooked
    if sys.platform != "win32":
        return _windows_only("fonts")
    from exo_control import win_native
    return win_native.fonts(step)


def dark_mode(step: Dict[str, Any]) -> Dict[str, Any]:
    hooked = _hook("dark_mode", step)
    if hooked is not None:
        return hooked
    if sys.platform != "win32":
        return _windows_only("dark_mode")
    from exo_control import win_native
    return win_native.dark_mode(step)
