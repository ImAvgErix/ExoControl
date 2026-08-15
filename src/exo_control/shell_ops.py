"""PowerShell / WSL / Docker — local runtimes. Mutating exec needs confirm=true."""
from __future__ import annotations

import shutil
import subprocess
import sys
from typing import Any, Callable, Dict, List, Optional

from exo_control.files_ops import _outside_denied, _resolve_under_roots
from exo_control.http_json import truncate
from exo_control.policy import parse_confirm

_RUN: Optional[Callable[[str, Dict[str, Any]], Optional[Dict[str, Any]]]] = None
_DOCKER_MUTATE = frozenset({"run", "rm", "remove", "stop", "kill", "exec", "pull", "build", "start"})


def _hook(op: str, step: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if _RUN is None:
        return None
    return _RUN(op, step)


def _windows_only(op: str) -> Dict[str, Any]:
    return {"ok": False, "error": f"{op} is Windows-only", "code": "WINDOWS_ONLY"}


def _run(args: List[str], timeout: float = 30.0, cwd: Optional[str] = None) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False, cwd=cwd)


def _cwd(step: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    path = str(step.get("cwd") or step.get("path") or "").strip()
    if not path:
        return None
    ok, resolved, outside = _resolve_under_roots(path)
    if not ok:
        return {"error": {"ok": False, "error": resolved, "code": "BAD_PATH"}}
    if outside:
        denied = _outside_denied("shell", resolved, parse_confirm(step.get("confirm", False)))
        if denied:
            return {"error": denied}
    return {"cwd": resolved}


def pwsh(step: Dict[str, Any]) -> Dict[str, Any]:
    if not parse_confirm(step.get("confirm", False)):
        return {"ok": False, "error": "pwsh requires confirm=true", "code": "CONFIRM_REQUIRED"}
    hooked = _hook("pwsh", step)
    if hooked is not None:
        return hooked
    script = str(step.get("script") or step.get("command") or step.get("code") or "").strip()
    if not script:
        return {"ok": False, "error": "pwsh requires script", "code": "MISSING_SCRIPT"}
    exe = shutil.which("pwsh") or shutil.which("powershell")
    if not exe:
        if sys.platform != "win32":
            return _windows_only("pwsh")
        return {"ok": False, "error": "pwsh/powershell not on PATH", "code": "UNAVAILABLE"}
    rooted = _cwd(step)
    if rooted and rooted.get("error"):
        return rooted["error"]
    try:
        proc = _run([exe, "-NoProfile", "-NonInteractive", "-Command", script], cwd=(rooted or {}).get("cwd"))
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return {"ok": False, "error": str(exc), "code": "UNAVAILABLE"}
    return {
        "ok": proc.returncode == 0,
        "stdout": truncate((proc.stdout or "").strip(), 4000),
        "stderr": truncate((proc.stderr or "").strip(), 400) if proc.stderr else "",
        "code": None if proc.returncode == 0 else "PWSH_ERROR",
        "error": None if proc.returncode == 0 else truncate((proc.stderr or f"exit {proc.returncode}").strip(), 400),
    }


def wsl(step: Dict[str, Any]) -> Dict[str, Any]:
    action = str(step.get("action") or "").lower()
    command = str(step.get("command") or step.get("script") or step.get("cmd") or "").strip()
    mutating = action in {"exec", "run", "command"} or bool(command)
    if mutating and not parse_confirm(step.get("confirm", False)):
        return {"ok": False, "error": "wsl exec requires confirm=true", "code": "CONFIRM_REQUIRED"}
    hooked = _hook("wsl", step)
    if hooked is not None:
        return hooked
    if sys.platform != "win32":
        return _windows_only("wsl")
    exe = shutil.which("wsl")
    if not exe:
        return {"ok": False, "error": "wsl not on PATH", "code": "UNAVAILABLE"}
    args = [exe]
    if mutating and command:
        distro = str(step.get("distro") or step.get("distribution") or "").strip()
        if distro:
            args.extend(["-d", distro])
        args.extend(["--", "sh", "-lc", command])
    else:
        args.extend(["-l", "-q"])
    try:
        proc = _run(args)
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return {"ok": False, "error": str(exc), "code": "UNAVAILABLE"}
    if mutating:
        return {
            "ok": proc.returncode == 0,
            "stdout": truncate((proc.stdout or "").strip(), 4000),
            "error": None if proc.returncode == 0 else truncate((proc.stderr or "wsl failed").strip(), 400),
        }
    distros = [ln.strip() for ln in (proc.stdout or "").splitlines() if ln.strip()]
    return {"ok": proc.returncode == 0, "distros": distros, "count": len(distros)}


def docker(step: Dict[str, Any]) -> Dict[str, Any]:
    action = str(step.get("action") or step.get("cmd") or "ps").lower()
    if action in _DOCKER_MUTATE and not parse_confirm(step.get("confirm", False)):
        return {"ok": False, "error": f"docker {action} requires confirm=true", "code": "CONFIRM_REQUIRED"}
    hooked = _hook("docker", step)
    if hooked is not None:
        return hooked
    exe = shutil.which("docker")
    if not exe:
        return {"ok": False, "error": "docker not on PATH", "code": "UNAVAILABLE"}
    args = [exe, action]
    image = str(step.get("image") or step.get("name") or "").strip()
    if action == "run" and image:
        args.extend(["--rm", image])
    elif action in {"rm", "stop", "kill", "start"} and (step.get("id") or step.get("container")):
        args.append(str(step.get("id") or step.get("container")))
    elif action == "ps":
        args.append("-a")
    try:
        proc = _run(args)
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return {"ok": False, "error": str(exc), "code": "UNAVAILABLE"}
    return {
        "ok": proc.returncode == 0,
        "action": action,
        "stdout": truncate((proc.stdout or "").strip(), 4000),
        "error": None if proc.returncode == 0 else truncate((proc.stderr or "docker failed").strip(), 400),
    }
