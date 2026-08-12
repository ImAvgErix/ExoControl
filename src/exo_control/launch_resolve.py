
"""Resolve fuzzy app names to launchable commands (Windows-first).

Order: explicit path → PATH/which → alias table → Start Menu .lnk scan →
shell execute for known aliases. Scores fuzzy name matches so installed
apps (Steam, Discord, Spot…) resolve without hard-coded paths.
"""
from __future__ import annotations

import os
import re
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


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
        r"%LOCALAPPDATA%\ExoLauncher\app\ExoLauncher.exe",
        r"%LOCALAPPDATA%\ExoLauncher\ExoLauncher.exe",
    ],
    "discord": [
        r"%LocalAppData%\Discord\Update.exe",
        "Discord.exe",
    ],
    "spotify": [
        r"%AppData%\Spotify\Spotify.exe",
        "Spotify.exe",
    ],
    "steam": [
        r"%ProgramFiles(x86)%\Steam\steam.exe",
        r"%ProgramFiles%\Steam\steam.exe",
        "steam.exe",
    ],
}


def _expand(p: str) -> str:
    return os.path.expandvars(os.path.expanduser(p))


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def _fuzzy_score(needle: str, candidate: str) -> float:
    """0..1 score: exact > startswith > token containment > subsequence."""
    n = _norm(needle)
    c = _norm(candidate)
    if not n or not c:
        return 0.0
    if n == c:
        return 1.0
    if c.startswith(n) or n.startswith(c):
        return 0.92
    if n in c:
        return 0.85
    if c in n:
        return 0.72
    nt, ct = set(n.split()), set(c.split())
    if nt and ct:
        overlap = len(nt & ct) / max(len(nt), len(ct))
        if overlap >= 0.5:
            return 0.55 + 0.3 * overlap
    # cheap char subsequence ratio
    i = 0
    for ch in c:
        if i < len(n) and ch == n[i]:
            i += 1
    if i == len(n) and len(n) >= 3:
        return 0.45
    return 0.0


def _start_menu_roots() -> List[Path]:
    roots: List[Path] = []
    for env_key, rel in (
        ("APPDATA", r"Microsoft\Windows\Start Menu\Programs"),
        ("PROGRAMDATA", r"Microsoft\Windows\Start Menu\Programs"),
    ):
        base = os.environ.get(env_key)
        if base:
            p = Path(base) / rel
            if p.is_dir():
                roots.append(p)
    # Common user-level installers drop shortcuts here too
    local = os.environ.get("LOCALAPPDATA")
    if local:
        for rel in (
            r"Microsoft\Windows\Start Menu\Programs",
        ):
            p = Path(local) / rel
            if p.is_dir() and p not in roots:
                roots.append(p)
    return roots


def _scan_start_menu(needle: str, limit: int = 40) -> List[Tuple[float, str, str]]:
    """Return ranked (score, display_name, .lnk path) hits."""
    hits: List[Tuple[float, str, str]] = []
    if os.name != "nt":
        return hits
    for root in _start_menu_roots():
        try:
            for lnk in root.rglob("*.lnk"):
                name = lnk.stem
                score = _fuzzy_score(needle, name)
                if score < 0.55:
                    continue
                hits.append((score, name, str(lnk)))
                if len(hits) >= limit * 3:
                    break
        except Exception:
            continue
    hits.sort(key=lambda t: t[0], reverse=True)
    return hits[:limit]


def _resolve_lnk_target(lnk_path: str) -> Optional[str]:
    """Best-effort resolve .lnk → target path (Windows COM / powershell fallback)."""
    if os.name != "nt":
        return None
    try:
        import win32com.client  # type: ignore

        shell = win32com.client.Dispatch("WScript.Shell")
        shortcut = shell.CreateShortCut(lnk_path)
        target = str(shortcut.Targetpath or "").strip()
        if target and Path(_expand(target)).exists():
            return str(Path(_expand(target)).resolve())
        # some shortcuts only have arguments + working dir; shell-open the .lnk itself
        return lnk_path if Path(lnk_path).is_file() else None
    except Exception:
        pass
    # PowerShell fallback (slower, no pywin32 required)
    try:
        import subprocess

        ps = (
            "$s = (New-Object -ComObject WScript.Shell).CreateShortcut('%s'); "
            "Write-Output $s.TargetPath"
        ) % lnk_path.replace("'", "''")
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
            capture_output=True,
            text=True,
            timeout=8,
            creationflags=int(getattr(subprocess, "CREATE_NO_WINDOW", 0)),
        )
        target = (proc.stdout or "").strip().splitlines()
        target = target[-1].strip() if target else ""
        if target and Path(_expand(target)).exists():
            return str(Path(_expand(target)).resolve())
        if Path(lnk_path).is_file():
            return lnk_path
    except Exception:
        pass
    return lnk_path if Path(lnk_path).is_file() else None


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
    looks_literal = (chr(92) in needle or "/" in needle or needle.lower().endswith((".exe", ".cmd", ".bat", ".lnk")))
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

    # Start Menu / Apps folder fuzzy scan
    menu_hits = _scan_start_menu(needle)
    if menu_hits:
        best_score, best_name, best_lnk = menu_hits[0]
        target = _resolve_lnk_target(best_lnk)
        if target:
            method = "start_menu_lnk" if target.lower().endswith(".lnk") else "start_menu"
            return {
                "ok": True,
                "command": target,
                "method": method,
                "app": needle,
                "matched": best_name,
                "score": round(best_score, 3),
                "shell": target.lower().endswith(".lnk"),
                "candidates": [h[1] for h in menu_hits[:8]],
            }

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

    return {
        "ok": False,
        "error": f"could not resolve app: {needle}",
        "candidates": tried[:12] + [h[1] for h in menu_hits[:6]],
    }
