"""Allowrooted git status/diff/log. No network; ``git -C`` only."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from exo_control.files_ops import _outside_denied, _resolve_under_roots
from exo_control.http_json import clip_int, truncate
from exo_control.policy import parse_confirm

_GIT = None
_ALLOWED = {
    "status": ["status", "--porcelain", "-b"],
    "diff": ["diff", "--stat"],
    "log": ["log", "-n", "8", "--oneline"],
}


def configured() -> bool:
    return shutil.which("git") is not None or _GIT is not None


def _run(repo: str, args: List[str], timeout: float = 20.0) -> Tuple[int, str, str]:
    if _GIT is not None:
        return _GIT(repo, args)
    try:
        proc = subprocess.run(
            ["git", "-C", repo, *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError:
        return 127, "", "git not found"
    except subprocess.TimeoutExpired:
        return 124, "", "git timed out"
    return int(proc.returncode), proc.stdout or "", proc.stderr or ""


def git(step: Dict[str, Any]) -> Dict[str, Any]:
    path = str(step.get("path") or step.get("repo") or step.get("cwd") or "").strip()
    if not path:
        return {"ok": False, "error": "git requires path", "code": "MISSING_PATH"}
    ok, resolved, outside = _resolve_under_roots(path)
    if not ok:
        return {"ok": False, "error": resolved, "code": "BAD_PATH"}
    denied = _outside_denied("git", resolved, parse_confirm(step.get("confirm", False))) if outside else None
    if denied:
        return denied
    target = Path(resolved)
    repo = str(target if target.is_dir() else target.parent)
    action = str(step.get("action") or step.get("cmd") or "status").lower().strip()
    if action not in _ALLOWED:
        return {"ok": False, "error": f"git action must be status|diff|log, not {action!r}", "code": "BAD_ACTION"}
    args = list(_ALLOWED[action])
    if action == "log":
        n = clip_int(step.get("max") or step.get("n") or 8, 8, 1, 40)
        args = ["log", "-n", str(n), "--oneline"]
    if action == "diff" and step.get("full"):
        args = ["diff"]
    code, stdout, stderr = _run(repo, args)
    if code == 127:
        return {"ok": False, "error": "git not found on PATH", "code": "UNAVAILABLE"}
    if code != 0 and "not a git repository" in (stderr or "").lower():
        return {"ok": False, "error": "not a git repository", "code": "NOT_FOUND", "path": repo}
    dirty = False
    if action == "status":
        lines = [ln for ln in stdout.splitlines() if ln and not ln.startswith("##")]
        dirty = bool(lines)
    return {
        "ok": code == 0,
        "action": action,
        "path": repo,
        "stdout": truncate(stdout.strip(), 4000),
        "stderr": truncate(stderr.strip(), 400) if stderr.strip() else "",
        "dirty": dirty if action == "status" else None,
        "code": None if code == 0 else "GIT_ERROR",
        "error": None if code == 0 else (stderr.strip() or f"git exited {code}"),
    }
