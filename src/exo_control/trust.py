"""Privilege / trust levels for Exo Control.

Default stays the current safety model. Trusted relaxes rate limits and lease
TTL. Full-Trust is explicit: operator env **and** a one-time human ack file,
plus an audit log. Kill-switch file always wins over the agent.
"""
from __future__ import annotations

import json
import os
import socket
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

ACK_PHRASE = "I own this PC"
LEVELS = ("default", "trusted", "full")
KILL_FILENAMES = ("KILL", "kill")


def _truthy(value: Any) -> bool:
    if value is True or value == 1:
        return True
    if value is False or value is None or value == 0:
        return False
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return False


def _env_raw(*keys: str) -> str:
    for key in keys:
        raw = (os.environ.get(key) or "").strip()
        if raw:
            return raw
    return ""


def requested_level() -> str:
    """Level the operator asked for via env (may not be active yet)."""
    if _truthy(_env_raw("EXO_FULL_TRUST", "AETHER_FULL_TRUST")):
        return "full"
    raw = _env_raw("EXO_TRUST", "AETHER_TRUST").lower().replace("_", "-")
    if raw in {"full", "full-trust", "fulltrust", "owner", "mine"}:
        return "full"
    if raw in {"trusted", "trust", "elevated"}:
        return "trusted"
    if raw in {"default", "safe", "sandbox", "off"}:
        return "default"
    return "default"


def ack_path() -> Path:
    from exo_control.paths import state_dir

    return state_dir() / "full_trust.ack"


def audit_path() -> Path:
    from exo_control.paths import state_dir

    return state_dir() / "trust_audit.jsonl"


def kill_paths() -> List[Path]:
    from exo_control.paths import exo_root, state_dir

    out: List[Path] = []
    seen = set()

    def _add(path: Path) -> None:
        key = str(path).lower()
        if key in seen:
            return
        seen.add(key)
        out.append(path)

    state = state_dir()
    for name in KILL_FILENAMES:
        _add(state / name)
    extra = _env_raw("EXO_KILL_PATH")
    if extra:
        _add(Path(extra).expanduser())
    # Isolated EXO_STATE_DIR (tests) must not inherit ~/.exo/KILL.
    env_home = _env_raw("EXO_HOME", "AETHER_HOME")
    env_state = _env_raw("EXO_STATE_DIR", "AETHER_STATE_DIR")
    if env_state and not env_home:
        return out
    root = exo_root()
    for name in KILL_FILENAMES:
        _add(root / name)
    return out


def kill_file_present() -> Optional[Path]:
    for path in kill_paths():
        try:
            if path.is_file():
                return path
        except OSError:
            continue
    return None


def kill_env_armed() -> bool:
    return _truthy(_env_raw("EXO_KILL_SWITCH", "AETHER_KILL_SWITCH"))


def human_kill_armed() -> bool:
    return kill_env_armed() or kill_file_present() is not None


def ack_present() -> bool:
    path = ack_path()
    if not path.is_file():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if not isinstance(data, dict):
        return False
    return bool(data.get("ack")) and str(data.get("phrase") or "") == ACK_PHRASE


def audit_append(event: str, **payload: Any) -> None:
    row = {"ts": time.time(), "event": event, **payload}
    try:
        path = audit_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
    except OSError:
        pass


def enable_full_trust(*, ack: str, confirm: bool = False, source: str = "op") -> Dict[str, Any]:
    """Write the one-time Full-Trust ack. Does not activate until env is set."""
    if not _truthy(confirm):
        return {
            "ok": False,
            "error": "trust_enable requires confirm=true and ack='I own this PC'",
        }
    if (ack or "").strip() != ACK_PHRASE:
        return {
            "ok": False,
            "error": f"ack must be exactly {ACK_PHRASE!r}",
            "hint": 'exo-control trust enable --ack "I own this PC"',
        }
    payload = {
        "ack": True,
        "phrase": ACK_PHRASE,
        "ts": time.time(),
        "user": os.environ.get("USERNAME") or os.environ.get("USER") or "",
        "host": socket.gethostname(),
        "source": source,
    }
    path = ack_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    audit_append("full_trust_ack", source=source, user=payload["user"], host=payload["host"])
    env_on = requested_level() == "full"
    return {
        "ok": True,
        "ack": True,
        "path": str(path),
        "active": env_on and True,
        "level": active_level(),
        "hint": (
            "Full-Trust is active"
            if env_on
            else "Ack recorded. Set EXO_TRUST=full (or EXO_FULL_TRUST=1) on the MCP/CLI process and restart it."
        ),
    }


def disable_ack() -> Dict[str, Any]:
    path = ack_path()
    existed = path.is_file()
    try:
        path.unlink(missing_ok=True)
    except OSError as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    audit_append("full_trust_ack_cleared")
    return {"ok": True, "cleared": existed, "level": active_level()}


def arm_kill_file() -> Dict[str, Any]:
    from exo_control.paths import exo_root

    path = exo_root() / "KILL"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("armed\n", encoding="utf-8")
    audit_append("kill_file_armed", path=str(path))
    return {"ok": True, "armed": True, "path": str(path), "kill_switch": True}


def clear_kill_file() -> Dict[str, Any]:
    """Operator-only: remove kill files. Agents must not call this to bypass."""
    removed: List[str] = []
    for path in kill_paths():
        try:
            if path.is_file():
                path.unlink()
                removed.append(str(path))
        except OSError:
            continue
    audit_append("kill_file_cleared", removed=removed)
    return {"ok": True, "removed": removed, "kill_switch": human_kill_armed()}


def full_trust_active() -> bool:
    return requested_level() == "full" and ack_present()


def active_level() -> str:
    req = requested_level()
    if req == "full":
        return "full" if ack_present() else "default"
    if req == "trusted":
        return "trusted"
    return "default"


def confirms_optional() -> bool:
    return full_trust_active()


def unrestricted() -> bool:
    """Full-Trust owner mode, or the elevated broker process itself."""
    try:
        from exo_control.elevate import in_broker

        if in_broker():
            return True
    except Exception:
        pass
    return full_trust_active()


def confirm_ok(value: Any, *, kind: str = "destructive") -> bool:
    """True when the step's confirm is set, or owner mode makes this kind optional.

    Default/trusted still hard-deny HKLM / anti-cheat / critical services /
    unnamed PID / system paths. Full-Trust (and the elevated broker) lift those.
    """
    if _truthy(value):
        return True
    if unrestricted():
        return True
    if kind in {"hklm", "anticheat", "critical_service", "unnamed_pid", "system_path"}:
        return False
    return confirms_optional()


def max_lease_ttl_sec(default: int = 1800) -> float:
    raw = _env_raw("EXO_LEASE_MAX_TTL", "AETHER_LEASE_MAX_TTL")
    if raw:
        try:
            return float(max(5, int(raw)))
        except ValueError:
            pass
    level = active_level()
    if level == "full":
        return float(max(default, 8 * 3600))
    if level == "trusted":
        return float(max(default, 4 * 3600))
    return float(max(5, default))


def default_lease_ttl_sec() -> float:
    level = active_level()
    if level == "full":
        return 1800.0
    if level == "trusted":
        return 600.0
    return 120.0


def rate_limit_multiplier() -> float:
    level = active_level()
    if level == "full":
        return 20.0
    if level == "trusted":
        return 3.0
    return 1.0


def min_action_interval_s(default: float = 0.04) -> float:
    if active_level() == "full":
        return 0.0
    return default


def extra_file_roots() -> List[Path]:
    """User-profile roots added in Full-Trust. Owner mode also unlocks the disk via allow_outside_roots."""
    if not full_trust_active():
        return []
    home = Path.home()
    extras = [
        home,
        home / "Documents",
        home / "Desktop",
        home / "Downloads",
        home / "Pictures",
        home / "Videos",
        home / "Music",
    ]
    userprofile = os.environ.get("USERPROFILE")
    if userprofile:
        extras.append(Path(userprofile))
    seen = set()
    out: List[Path] = []
    for p in extras:
        try:
            r = p.expanduser().resolve()
        except OSError:
            continue
        key = str(r).lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


def _windows_protected_prefixes() -> List[Path]:
    prefixes: List[Path] = []
    windir = os.environ.get("WINDIR") or r"C:\Windows"
    prefixes.append(Path(windir))
    systemdrive = os.environ.get("SystemDrive") or "C:"
    prefixes.extend(
        [
            Path(systemdrive) / "Windows",
            Path(systemdrive) / "Program Files",
            Path(systemdrive) / "Program Files (x86)",
            Path(systemdrive) / "ProgramData" / "Microsoft",
        ]
    )
    return prefixes


def is_protected_system_path(path: str | Path) -> bool:
    """True for OS / program-files trees (default/trusted) and the kill-switch file.

    Full-Trust / elevated broker may write Windows and Program Files. The
    human kill-switch file stays untouchable so an agent cannot disarm it.
    """
    try:
        resolved = Path(path).expanduser().resolve()
    except Exception:
        return True
    for kp in kill_paths():
        try:
            if resolved == kp.resolve():
                return True
        except OSError:
            continue
    if unrestricted():
        return False
    low = str(resolved).lower()
    for prefix in _windows_protected_prefixes():
        try:
            pre = str(prefix.resolve()).lower()
        except OSError:
            pre = str(prefix).lower()
        if low == pre or low.startswith(pre.rstrip("\\/") + os.sep.lower()) or low.startswith(pre.rstrip("\\/") + "\\"):
            return True
        # also match forward slashes
        if low.startswith(pre.replace("\\", "/")):
            return True
    return False


def status() -> Dict[str, Any]:
    req = requested_level()
    ack = ack_present()
    active = active_level()
    kill = kill_file_present()
    out: Dict[str, Any] = {
        "ok": True,
        "requested": req,
        "ack": ack,
        "level": active,
        "full_trust": active == "full",
        "unrestricted": unrestricted(),
        "confirms_optional": confirms_optional(),
        "kill_switch_file": str(kill) if kill else None,
        "kill_switch_env": kill_env_armed(),
        "human_kill": human_kill_armed(),
        "ack_phrase": ACK_PHRASE,
        "max_lease_ttl_sec": max_lease_ttl_sec(),
        "hint": None,
    }
    if req == "full" and not ack:
        out["hint"] = (
            'Full-Trust env is set but ack is missing. Run: '
            'exo-control trust enable --ack "I own this PC"'
        )
    elif ack and req != "full":
        out["hint"] = "Ack exists but EXO_TRUST=full (or EXO_FULL_TRUST=1) is not set on this process."
    elif active == "full":
        out["hint"] = (
            "Full-Trust owner mode: no Exo policy denials. Privileged OS ops "
            "auto-elevate via the broker (one UAC to install). Kill file ~/.exo/KILL still wins."
        )
    return out


def snapshot_for_identity() -> Dict[str, Any]:
    st = status()
    return {
        "level": st["level"],
        "requested": st["requested"],
        "ack": st["ack"],
        "full_trust": st["full_trust"],
        "unrestricted": st.get("unrestricted"),
        "confirms_optional": st["confirms_optional"],
        "human_kill": st["human_kill"],
    }
