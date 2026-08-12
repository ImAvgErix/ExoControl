"""Exo Control home / state / lock paths.

Preferred root: ``~/.exo`` (override with ``EXO_HOME``).
Legacy root: ``~/.aether`` (still read for migration / AETHER_* env).

Env (preferred → legacy):
  EXO_HOME / AETHER_HOME
  EXO_STATE_DIR / AETHER_STATE_DIR
  EXO_LOCK_DIR / AETHER_LOCK_DIR
  EXO_FILE_ROOTS / AETHER_FILE_ROOTS
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import List, Optional


def user_home() -> Path:
    for key in ("USERPROFILE", "HOME"):
        raw = (os.environ.get(key) or "").strip()
        if raw:
            return Path(raw)
    return Path.home()


def _env_path(*keys: str) -> Optional[Path]:
    for key in keys:
        raw = (os.environ.get(key) or "").strip()
        if raw:
            return Path(raw).expanduser()
    return None


def exo_root() -> Path:
    """Product data root: ``~/.exo`` (or EXO_HOME), with ``~/.aether`` migration."""
    explicit = _env_path("EXO_HOME", "AETHER_HOME")
    if explicit is not None:
        # If AETHER_HOME points at a parent (user profile), append product dir.
        name = explicit.name.lower()
        if name in {".exo", ".aether"}:
            return explicit
        # Explicit product home path
        if (explicit / "state").exists() or (explicit / "locks").exists():
            return explicit
        # Treat as user home override
        preferred = explicit / ".exo"
        legacy = explicit / ".aether"
        if preferred.exists() or not legacy.exists():
            return preferred
        return legacy

    home = user_home()
    preferred = home / ".exo"
    legacy = home / ".aether"
    if preferred.exists():
        return preferred
    if legacy.exists() and not preferred.exists():
        # Soft migration: create .exo and leave legacy in place; readers fall back.
        try:
            preferred.mkdir(parents=True, exist_ok=True)
            for sub in ("state", "locks", "workspace"):
                src = legacy / sub
                dst = preferred / sub
                if src.exists() and not dst.exists():
                    try:
                        if src.is_dir():
                            shutil.copytree(src, dst, dirs_exist_ok=True)
                        else:
                            dst.parent.mkdir(parents=True, exist_ok=True)
                            shutil.copy2(src, dst)
                    except OSError:
                        pass
            cfg = legacy / "config.json"
            if cfg.exists() and not (preferred / "config.json").exists():
                try:
                    shutil.copy2(cfg, preferred / "config.json")
                except OSError:
                    pass
        except OSError:
            return legacy
        return preferred
    preferred.mkdir(parents=True, exist_ok=True)
    return preferred


def state_dir() -> Path:
    p = _env_path("EXO_STATE_DIR", "AETHER_STATE_DIR")
    if p is not None:
        p.mkdir(parents=True, exist_ok=True)
        return p
    d = exo_root() / "state"
    d.mkdir(parents=True, exist_ok=True)
    # legacy fallback for readers if new state empty and legacy has data
    return d


def lock_dir() -> Path:
    p = _env_path("EXO_LOCK_DIR", "AETHER_LOCK_DIR")
    if p is not None:
        p.mkdir(parents=True, exist_ok=True)
        return p
    d = exo_root() / "locks"
    d.mkdir(parents=True, exist_ok=True)
    return d


def workspace_dir() -> Path:
    d = exo_root() / "workspace"
    d.mkdir(parents=True, exist_ok=True)
    return d


def config_path() -> Path:
    return exo_root() / "config.json"


def legacy_aether_root() -> Path:
    return user_home() / ".aether"


def file_roots() -> List[Path]:
    roots: List[Path] = [workspace_dir().resolve()]
    # Always include legacy workspace if present (compat)
    leg = legacy_aether_root() / "workspace"
    if leg.exists():
        try:
            roots.append(leg.resolve())
        except OSError:
            pass
    extra = os.environ.get("EXO_FILE_ROOTS") or os.environ.get("AETHER_FILE_ROOTS") or ""
    if extra.strip():
        for part in extra.split(os.pathsep):
            part = part.strip()
            if not part:
                continue
            try:
                roots.append(Path(part).expanduser().resolve())
            except OSError:
                continue
    # de-dupe
    seen = set()
    out: List[Path] = []
    for r in roots:
        key = str(r).lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out
