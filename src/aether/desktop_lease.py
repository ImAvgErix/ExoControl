"""Exclusive multi-agent desktop lease (Windows-safe file lock).

Lock file:  <home>/.exo/locks/desktop.lock
Lease JSON: <home>/.exo/state/desktop_lease.json

Home resolution: see ``aether.paths`` (``.exo`` preferred, ``.aether`` legacy).
"""
from __future__ import annotations

import json
import os
import secrets
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, Optional

from aether.paths import lock_dir as _lock_dir
from aether.paths import state_dir as _state_dir


def _lock_path() -> Path:
    return _lock_dir() / "desktop.lock"


def _lease_path() -> Path:
    return _state_dir() / "desktop_lease.json"


def _focus_path() -> Path:
    return _state_dir() / "last_focus.json"


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def _ensure_dirs() -> None:
    _lock_dir().mkdir(parents=True, exist_ok=True)
    _state_dir().mkdir(parents=True, exist_ok=True)


@contextmanager
def _exclusive(timeout: float = 5.0, poll: float = 0.05) -> Iterator[None]:
    """Acquire exclusive OS lock on desktop.lock for atomic lease RMW."""
    _ensure_dirs()
    path = _lock_path()
    deadline = time.time() + timeout
    fh = open(path, "a+b")
    try:
        if fh.tell() == 0 and fh.read(1) == b"":
            fh.write(b"\0")
            fh.flush()
        while True:
            try:
                fh.seek(0)
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.time() >= deadline:
                    fh.close()
                    raise TimeoutError(f"Could not acquire lock: {path}")
                time.sleep(poll)
        yield
    finally:
        try:
            fh.seek(0)
            if os.name == "nt":
                import msvcrt

                try:
                    msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
                except OSError:
                    pass
            else:
                import fcntl

                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        finally:
            fh.close()


def _load_unlocked() -> Optional[Dict[str, Any]]:
    path = _lease_path()
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _save_unlocked(lease: Optional[Dict[str, Any]]) -> None:
    path = _lease_path()
    if lease is None:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
        return
    path.write_text(json.dumps(lease, indent=2), encoding="utf-8")


def _active(lease: Optional[Dict[str, Any]], now: Optional[float] = None) -> bool:
    if not lease or not lease.get("token"):
        return False
    now = time.time() if now is None else now
    try:
        return float(lease.get("expires_at") or 0) > now
    except (TypeError, ValueError):
        return False


def _conflict(lease: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "ok": False,
        "holder": lease.get("agent_id"),
        "task": lease.get("task"),
        "expires_at": _iso(float(lease.get("expires_at") or 0)),
    }


def acquire(agent_id: str, task: str = "", ttl_sec: float = 120) -> Dict[str, Any]:
    agent_id = str(agent_id or "").strip()
    task = str(task or "").strip() or "unspecified"
    if not agent_id:
        return {"ok": False, "error": "agent_id required"}
    ttl_sec = max(0.05, float(ttl_sec))
    with _exclusive():
        now = time.time()
        lease = _load_unlocked()
        if _active(lease, now):
            return _conflict(lease)  # type: ignore[arg-type]
        token = secrets.token_hex(16)
        expires = now + ttl_sec
        new_lease = {
            "token": token,
            "agent_id": agent_id,
            "task": task,
            "acquired_at": now,
            "expires_at": expires,
            "last_focus": (lease or {}).get("last_focus"),
        }
        _save_unlocked(new_lease)
        return {"ok": True, "token": token, "expires_at": _iso(expires)}


def renew(token: str, ttl_sec: float = 120) -> Dict[str, Any]:
    token = str(token or "").strip()
    if not token:
        return {"ok": False, "error": "token required"}
    ttl_sec = max(0.05, float(ttl_sec))
    with _exclusive():
        now = time.time()
        lease = _load_unlocked()
        if not lease or lease.get("token") != token:
            return {"ok": False, "error": "invalid lease token"}
        if not _active(lease, now):
            _save_unlocked(None)
            return {"ok": False, "error": "lease expired"}
        expires = now + ttl_sec
        lease["expires_at"] = expires
        _save_unlocked(lease)
        return {"ok": True, "token": token, "expires_at": _iso(expires)}


def release(token: str) -> Dict[str, Any]:
    token = str(token or "").strip()
    if not token:
        return {"ok": False, "error": "token required"}
    with _exclusive():
        lease = _load_unlocked()
        if not lease or not lease.get("token"):
            return {"ok": True, "released": False, "reason": "no lease"}
        if lease.get("token") != token:
            if _active(lease):
                out = {"ok": False, "error": "token mismatch"}
                out.update(_conflict(lease))
                return out
            _save_unlocked(None)
            return {"ok": True, "released": False, "reason": "expired"}
        last_focus = lease.get("last_focus")
        _save_unlocked(None)
        if last_focus:
            try:
                _focus_path().write_text(json.dumps(last_focus, indent=2), encoding="utf-8")
            except OSError:
                pass
        return {"ok": True, "released": True}



def force_release(token: Optional[str] = None, agent_id: Optional[str] = None) -> Dict[str, Any]:
    """Clear a lease by token, holder agent_id, expired state, or unconditional force.

    Used for cross-process cleanup when the acquiring engine is gone / sticky claim.
    """
    token = str(token or "").strip() or None
    agent_id = str(agent_id or "").strip() or None
    with _exclusive():
        lease = _load_unlocked()
        if not lease or not lease.get("token"):
            return {"ok": True, "released": False, "reason": "no lease", "forced": True}
        active = _active(lease)
        match_token = bool(token and lease.get("token") == token)
        match_agent = bool(agent_id and lease.get("agent_id") == agent_id)
        # Unconditional force when neither filter provided; else require match or expired.
        if token or agent_id:
            if not (match_token or match_agent or not active):
                out = {"ok": False, "error": "token/agent mismatch", "forced": True}
                if active:
                    out.update(_conflict(lease))
                return out
        last_focus = lease.get("last_focus")
        _save_unlocked(None)
        if last_focus:
            try:
                _focus_path().write_text(json.dumps(last_focus, indent=2), encoding="utf-8")
            except OSError:
                pass
        reason = "token" if match_token else ("agent" if match_agent else ("expired" if not active else "forced"))
        return {"ok": True, "released": True, "forced": True, "reason": reason}


def status() -> Dict[str, Any]:
    with _exclusive():
        now = time.time()
        lease = _load_unlocked()
        if not lease or not lease.get("token"):
            return {"ok": True, "held": False, "last_focus": load_last_focus()}
        if not _active(lease, now):
            last_focus = lease.get("last_focus")
            _save_unlocked(None)
            if last_focus:
                try:
                    _focus_path().write_text(json.dumps(last_focus, indent=2), encoding="utf-8")
                except OSError:
                    pass
            return {
                "ok": True,
                "held": False,
                "expired": True,
                "last_holder": lease.get("agent_id"),
                "task": lease.get("task"),
                "expires_at": _iso(float(lease.get("expires_at") or 0)),
                "last_focus": last_focus or load_last_focus(),
            }
        return {
            "ok": True,
            "held": True,
            "holder": lease.get("agent_id"),
            "agent_id": lease.get("agent_id"),
            "task": lease.get("task"),
            "token": lease.get("token"),
            "expires_at": _iso(float(lease["expires_at"])),
            "last_focus": lease.get("last_focus"),
        }


def validate(token: str) -> bool:
    token = str(token or "").strip()
    if not token:
        return False
    with _exclusive():
        lease = _load_unlocked()
        return bool(lease and lease.get("token") == token and _active(lease))


def set_last_focus(token: str, focus: Any) -> None:
    """Best-effort persist last focus under an active lease + state/last_focus.json."""
    token = str(token or "").strip()
    if not token:
        return
    try:
        with _exclusive():
            lease = _load_unlocked()
            if lease and lease.get("token") == token and _active(lease):
                lease["last_focus"] = focus
                _save_unlocked(lease)
        persist_last_focus(focus)
    except Exception:
        pass


def persist_last_focus(focus: Any) -> None:
    _ensure_dirs()
    try:
        _focus_path().write_text(json.dumps(focus, indent=2), encoding="utf-8")
    except OSError:
        pass


def load_last_focus() -> Optional[Dict[str, Any]]:
    path = _focus_path()
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None
