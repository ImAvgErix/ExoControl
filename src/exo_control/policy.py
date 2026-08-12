"""Central operator policy for Exo Control.

The agent that writes step JSON is not a human. Flags in this module are the
only way the *operator* (env / config) expands power. ``confirm=true`` in a
step is an agent assertion, not a second factor — destructive ops still need
it, but it never widens filesystem roots or steals a lease by itself.
"""
from __future__ import annotations

import os
import re
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import urlparse


PRODUCT = "Exo Control"
ENGINE = "ExoExecEngine"

# Secret-ish env names (value withheld unless EXO_ALLOW_ENV_VALUES=1).
_SECRET_ENV_RE = re.compile(
    r"(api[_-]?key|access[_-]?token|auth|secret|password|passwd|pwd|"
    r"credential|private[_-]?key|bearer|session|oauth|jwt|conn(ection)?[_-]?str)",
    re.I,
)

_DANGEROUS_LAUNCH_STEMS = frozenset({
    "powershell", "powershell_ise", "pwsh", "cmd", "command",
    "mshta", "wscript", "cscript", "regsvr32", "rundll32",
    "bitsadmin", "certutil", "msiexec", "mmh", "bash", "wsl",
})

_DANGEROUS_OPEN_SUFFIXES = (
    ".ps1", ".bat", ".cmd", ".vbs", ".js", ".jse", ".wsf", ".hta",
    ".msc", ".scr", ".com", ".msi", ".reg",
)

CRITICAL_SERVICES = frozenset({
    "windefend", "wdfilter", "sense", "securityhealthservice",
    "eventlog", "rpcss", "dcomlaunch", "lanmanserver", "lanmanworkstation",
    "wuauserv", "bits", "cryptsvc", "plugplay", "power", "samss", "lsass",
    "winmgmt", "schedule", "profsvc", "userprofile service",
})


def env_flag(*keys: str, default: bool = False) -> bool:
    for key in keys:
        raw = (os.environ.get(key) or "").strip().lower()
        if raw in {"1", "true", "yes", "on"}:
            return True
        if raw in {"0", "false", "no", "off"}:
            return False
    return default


def env_int(*keys: str, default: int) -> int:
    for key in keys:
        raw = (os.environ.get(key) or "").strip()
        if not raw:
            continue
        try:
            return int(raw)
        except ValueError:
            continue
    return default


def parse_confirm(value: Any) -> bool:
    """True only for real JSON true / 1 / 'true'. ``bool('false')`` is a footgun."""
    if value is True or value == 1:
        return True
    if value is False or value is None or value == 0:
        return False
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return False


def allow_force_release() -> bool:
    return env_flag("EXO_ALLOW_FORCE_RELEASE", "AETHER_ALLOW_FORCE_RELEASE", default=False)


def allow_outside_roots() -> bool:
    """Operator must opt in before confirm can touch paths outside allowroots."""
    return env_flag("EXO_ALLOW_OUTSIDE_ROOTS", "AETHER_ALLOW_OUTSIDE_ROOTS", default=False)


def allow_env_values() -> bool:
    return env_flag("EXO_ALLOW_ENV_VALUES", "AETHER_ALLOW_ENV_VALUES", default=False)


def deny_browser_eval() -> bool:
    return env_flag("EXO_DENY_BROWSER_EVAL", default=False)


def allow_mcp_aliases() -> bool:
    return env_flag("EXO_MCP_ALIASES", "AETHER_MCP_ALIASES", default=False)


def allow_screenshot_on_fail_default() -> bool:
    return env_flag("EXO_SCREENSHOT_ON_FAIL", default=False)


def max_lease_ttl_sec() -> float:
    return float(max(5, env_int("EXO_LEASE_MAX_TTL", "AETHER_LEASE_MAX_TTL", default=1800)))


def is_secret_env_name(name: str) -> bool:
    return bool(name and _SECRET_ENV_RE.search(name))


def redact_env_value(name: str, value: str) -> Dict[str, Any]:
    if allow_env_values() or not is_secret_env_name(name):
        out = value
        if len(out) > 2000:
            out = out[:1997] + "..."
        return {"ok": True, "name": name, "value": out, "redacted": False}
    return {
        "ok": True,
        "name": name,
        "value": None,
        "redacted": True,
        "hint": "set EXO_ALLOW_ENV_VALUES=1 to return secret-like values",
    }


def is_loopback_endpoint(endpoint: str) -> bool:
    raw = (endpoint or "").strip()
    if not raw:
        return False
    if "://" not in raw:
        raw = "http://" + raw
    try:
        parsed = urlparse(raw)
    except Exception:
        return False
    host = (parsed.hostname or "").strip().lower()
    return host in {"127.0.0.1", "localhost", "::1"}


def is_dangerous_launch(command: str) -> bool:
    from pathlib import Path

    stem = Path(str(command or "")).stem.lower()
    return stem in _DANGEROUS_LAUNCH_STEMS


def open_needs_confirm(target: str) -> bool:
    t = (target or "").strip().lower()
    if not t:
        return False
    if t.startswith(("http://", "https://", "mailto:")):
        return False
    return t.endswith(_DANGEROUS_OPEN_SUFFIXES)


def sanitize_cdp_endpoints(endpoints: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Drop websocket debugger URLs from lease-free discovery."""
    out: List[Dict[str, Any]] = []
    for item in endpoints or []:
        if not isinstance(item, dict):
            continue
        row = dict(item)
        row.pop("ws", None)
        row.pop("webSocketDebuggerUrl", None)
        targets = []
        for t in row.get("targets") or []:
            if not isinstance(t, dict):
                continue
            tt = dict(t)
            tt.pop("webSocketDebuggerUrl", None)
            targets.append(tt)
        row["targets"] = targets
        out.append(row)
    return out


def identity() -> Dict[str, Any]:
    from exo_control import __version__
    import exo_control as aether

    path = getattr(aether, "__file__", "") or ""
    return {
        "product": PRODUCT,
        "version": __version__,
        "engine": ENGINE,
        "module": path,
        "policy": {
            "allow_force_release": allow_force_release(),
            "allow_outside_roots": allow_outside_roots(),
            "allow_env_values": allow_env_values(),
            "deny_browser_eval": deny_browser_eval(),
            "mcp_aliases": allow_mcp_aliases(),
            "max_lease_ttl_sec": max_lease_ttl_sec(),
        },
    }


def shadow_warnings(sys_path: Optional[List[str]] = None, aether_file: str = "") -> List[str]:
    import sys
    from pathlib import Path

    path_entries = [Path(p) for p in (sys_path if sys_path is not None else sys.path) if p]
    warnings: List[str] = []
    aether_path = Path(aether_file) if aether_file else Path()
    hits = [str(p) for p in path_entries if "aether-driver" in str(p) or "exo-control" in str(p).lower() or "ExoControl" in str(p)]
    if any("aether-driver" in h for h in hits) and "aether-driver" in str(aether_path):
        warnings.append(
            "import resolves to ~/.aether/aether-driver — remove leftover "
            "__editable__.aether_driver-*.pth or drop PYTHONPATH so pip install wins"
        )
    site = Path(sys.prefix) / "Lib" / "site-packages"
    if site.exists():
        for pth in site.glob("__editable__.aether_driver-*.pth"):
            warnings.append(f"stale editable pth: {pth}")
    docs = Path.home() / "Documents" / "exo-control"
    if docs.exists() and "Documents" in str(aether_path) and "exo-control" in str(aether_path):
        warnings.append(
            f"importing stale checkout {docs} — use the 1.3+ ExoControl tree or pip install the git tag"
        )
    return warnings
