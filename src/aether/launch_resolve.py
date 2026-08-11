
"""Resolve fuzzy app names to launchable commands (Windows-first)."""
from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional


_ALIASES: Dict[str, List[str]] = {
    "notepad": ["notepad.exe", "notepad"],
    "calc": ["calc.exe", "calculator"],
    "calculator": ["calc.exe", "calculator"],
    "cmd": ["cmd.exe"],
    "powershell": ["powershell.exe", "pwsh.exe"],
    "pwsh": ["pwsh.exe", "powershell.exe"],
    "explorer": ["explorer.exe"],
    "chrome": [
        "chrome.exe",
        r"%ProgramFiles%\Google\Chrome\Application\chrome.exe",
        r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe",
        r"%LocalAppData%\Google\Chrome\Application\chrome.exe",
    ],
    "msedge": [
        "msedge.exe",
        r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe",
        r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe",
    ],
    "edge": [
        "msedge.exe",
        r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe",
    ],
    "code": [
        "code.cmd",
        "code.exe",
        r"%LocalAppData%\Programs\Microsoft VS Code\Code.exe",
    ],
    "exo": [
        r"%USERPROFILE%\Documents\exo-launcher\ExoLauncher\bin\x64\Debug\net8.0-windows10.0.19041.0\ExoLauncher.exe",
        r"%LOCALAPPDATA%\ExoLauncher\ExoLauncher.exe",
    ],
}


def _expand(p: str) -> str:
    return os.path.expandvars(os.path.expanduser(p))


def resolve_launch_target(
    raw: Optional[str] = None,
    *,
    app: Optional[str] = None,
    name: Optional[str] = None,
    query: Optional[str] = None,
) -> Dict[str, Any]:
    """Resolve command/path/exe/app/name into a concrete launch target."""
    needle = (app or name or query or raw or "").strip()
    if not needle:
        return {"ok": False, "error": "launch requires command/path/exe/app"}

    expanded = _expand(needle)
    p = Path(expanded)
    if p.is_file():
        return {"ok": True, "command": str(p.resolve()), "method": "path", "app": needle}

    # Explicit path/exe from caller: trust it even if missing (Popen reports FileNotFound).
    looks_literal = (chr(92) in needle or "/" in needle or needle.lower().endswith((".exe", ".cmd", ".bat")))
    if looks_literal:
        return {"ok": True, "command": expanded, "method": "path_literal", "app": needle}

    hit = shutil.which(needle) or shutil.which(expanded)
    if hit:
        return {"ok": True, "command": hit, "method": "path_which", "app": needle}

    key = Path(needle).stem.lower()
    candidates: List[str] = list(_ALIASES.get(key, []))
    if not needle.lower().endswith(".exe"):
        candidates.append(f"{key}.exe")
    candidates.append(key)

    tried: List[str] = []
    for cand in candidates:
        cexp = _expand(cand)
        tried.append(cexp)
        cp = Path(cexp)
        if cp.is_file():
            return {"ok": True, "command": str(cp.resolve()), "method": "alias_path", "app": needle}
        which = shutil.which(cexp) or shutil.which(Path(cexp).name)
        if which:
            return {"ok": True, "command": which, "method": "alias_which", "app": needle}

    # Known alias that still needs shell open (e.g. Start Menu app id)
    if os.name == "nt" and key in _ALIASES:
        return {
            "ok": True,
            "command": needle,
            "method": "shell_execute",
            "app": needle,
            "shell": True,
            "candidates": tried[:12],
        }

    return {"ok": False, "error": f"could not resolve app: {needle}", "candidates": tried[:12]}
