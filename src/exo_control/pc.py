"""The rest of the PC — owner-mode primitives a person in the chair can do.

No new packages. ctypes + stdlib + netsh/winget when present.
Mutating ops (sleep, wifi_connect, recycle_empty, package install, wallpaper set)
go through the same confirm / Full-Trust gate as the rest of Exo Control.
"""
from __future__ import annotations

import ctypes
import hashlib
import os
import shutil
import subprocess
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence


def _run(cmd: List[str], timeout: float = 20.0) -> subprocess.CompletedProcess:
    flags = int(getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
        creationflags=flags,
    )


def _confirm_ok(confirm: bool, *, kind: str = "destructive") -> bool:
    from exo_control.policy import confirm_ok

    return confirm_ok(confirm, kind=kind)


def _win() -> bool:
    return os.name == "nt"


# ── clock / idle / power ─────────────────────────────────────────────

def clock() -> Dict[str, Any]:
    now = datetime.now().astimezone()
    utc = datetime.now(timezone.utc)
    return {
        "ok": True,
        "local": now.isoformat(timespec="seconds"),
        "utc": utc.isoformat(timespec="seconds").replace("+00:00", "Z"),
        "tz": now.tzname() or "",
        "epoch": int(time.time()),
    }


def idle() -> Dict[str, Any]:
    if not _win():
        return {"ok": False, "error": "idle is Windows-only"}
    class LASTINPUTINFO(ctypes.Structure):
        _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]

    info = LASTINPUTINFO()
    info.cbSize = ctypes.sizeof(LASTINPUTINFO)
    if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):
        return {"ok": False, "error": "GetLastInputInfo failed"}
    tick = ctypes.windll.kernel32.GetTickCount()
    idle_ms = int(tick - info.dwTime) if tick >= info.dwTime else 0
    return {"ok": True, "idle_ms": idle_ms, "idle_s": round(idle_ms / 1000.0, 2)}


def power() -> Dict[str, Any]:
    if not _win():
        return {"ok": False, "error": "power is Windows-only"}

    class SYSTEM_POWER_STATUS(ctypes.Structure):
        _fields_ = [
            ("ACLineStatus", ctypes.c_ubyte),
            ("BatteryFlag", ctypes.c_ubyte),
            ("BatteryLifePercent", ctypes.c_ubyte),
            ("SystemStatusFlag", ctypes.c_ubyte),
            ("BatteryLifeTime", ctypes.c_uint32),
            ("BatteryFullLifeTime", ctypes.c_uint32),
        ]

    st = SYSTEM_POWER_STATUS()
    if not ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(st)):
        return {"ok": False, "error": "GetSystemPowerStatus failed"}
    ac = {0: "battery", 1: "ac", 255: "unknown"}.get(int(st.ACLineStatus), "unknown")
    pct = int(st.BatteryLifePercent)
    out: Dict[str, Any] = {
        "ok": True,
        "ac": ac,
        "on_ac": ac == "ac",
        "percent": None if pct > 100 else pct,
        "lifetime_s": None if int(st.BatteryLifeTime) == 0xFFFFFFFF else int(st.BatteryLifeTime),
    }
    try:
        plan = _run(["powercfg", "/getactivescheme"], timeout=8)
        line = (plan.stdout or "").strip()
        if line:
            out["plan"] = line.split("(")[-1].rstrip(")") if "(" in line else line
            out["plan_raw"] = line[:200]
    except Exception:
        pass
    return out


def lock() -> Dict[str, Any]:
    if not _win():
        return {"ok": False, "error": "lock is Windows-only"}
    ok = bool(ctypes.windll.user32.LockWorkStation())
    return {"ok": ok, "locked": ok} if ok else {"ok": False, "error": "LockWorkStation failed"}


def sleep(*, confirm: bool = False) -> Dict[str, Any]:
    if not _confirm_ok(confirm, kind="sleep"):
        return {"ok": False, "error": "sleep requires confirm=true"}
    if not _win():
        return {"ok": False, "error": "sleep is Windows-only"}
    try:
        powrprof = ctypes.windll.powrprof
        # SetSuspendState(hibernate, forceCritical, disableWakeEvent)
        ok = bool(powrprof.SetSuspendState(False, False, False))
        return {"ok": ok, "sleeping": ok} if ok else {"ok": False, "error": "SetSuspendState failed"}
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


# ── audio ────────────────────────────────────────────────────────────

def _audio_volume_iface():
    """IAudioEndpointVolume for the default render device, or None."""
    if not _win():
        return None
    ole32 = ctypes.windll.ole32
    ole32.CoInitialize(None)

    class GUID(ctypes.Structure):
        _fields_ = [
            ("Data1", ctypes.c_uint32),
            ("Data2", ctypes.c_uint16),
            ("Data3", ctypes.c_uint16),
            ("Data4", ctypes.c_ubyte * 8),
        ]

    def guid(s: str) -> GUID:
        g = GUID()
        ole32.CLSIDFromString(ctypes.c_wchar_p(s), ctypes.byref(g))
        return g

    CLSID_MMDeviceEnumerator = guid("{BCDE0395-E52F-467C-8E3D-C4579291692E}")
    IID_IMMDeviceEnumerator = guid("{A95664D2-9614-4F35-A746-DE8DB63617E6}")
    IID_IAudioEndpointVolume = guid("{5CDF2C82-841E-4546-9722-0CF74078229A}")

    enumerator = ctypes.c_void_p()
    hr = ole32.CoCreateInstance(
        ctypes.byref(CLSID_MMDeviceEnumerator),
        None,
        1,  # CLSCTX_INPROC_SERVER
        ctypes.byref(IID_IMMDeviceEnumerator),
        ctypes.byref(enumerator),
    )
    if hr != 0 or not enumerator:
        return None

    # IMMDeviceEnumerator::GetDefaultAudioEndpoint is vtable slot 4
    # HRESULT GetDefaultAudioEndpoint(EDataFlow, ERole, IMMDevice**)
    get_default = ctypes.WINFUNCTYPE(
        ctypes.HRESULT,
        ctypes.c_void_p,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.POINTER(ctypes.c_void_p),
    )
    vtbl = ctypes.cast(enumerator, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    fn_get = get_default(vtbl[4])
    device = ctypes.c_void_p()
    hr = fn_get(enumerator, 0, 1, ctypes.byref(device))  # eRender, eMultimedia
    if hr != 0 or not device:
        return None

    # IMMDevice::Activate slot 3
    activate = ctypes.WINFUNCTYPE(
        ctypes.HRESULT,
        ctypes.c_void_p,
        ctypes.POINTER(GUID),
        ctypes.c_uint32,
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_void_p),
    )
    dvtbl = ctypes.cast(device, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    fn_act = activate(dvtbl[3])
    volume = ctypes.c_void_p()
    hr = fn_act(device, ctypes.byref(IID_IAudioEndpointVolume), 1, None, ctypes.byref(volume))
    if hr != 0 or not volume:
        return None
    return volume


def _audio_scalar(volume, set_to: Optional[float] = None) -> Optional[float]:
    vtbl = ctypes.cast(volume, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    if set_to is None:
        get_s = ctypes.WINFUNCTYPE(
            ctypes.HRESULT, ctypes.c_void_p, ctypes.POINTER(ctypes.c_float)
        )(vtbl[9])  # GetMasterVolumeLevelScalar
        val = ctypes.c_float()
        if get_s(volume, ctypes.byref(val)) != 0:
            return None
        return float(val.value)
    set_s = ctypes.WINFUNCTYPE(
        ctypes.HRESULT, ctypes.c_void_p, ctypes.c_float, ctypes.c_void_p
    )(vtbl[7])  # SetMasterVolumeLevelScalar
    if set_s(volume, ctypes.c_float(max(0.0, min(1.0, set_to))), None) != 0:
        return None
    return float(max(0.0, min(1.0, set_to)))


def _audio_mute(volume, set_to: Optional[bool] = None) -> Optional[bool]:
    vtbl = ctypes.cast(volume, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    if set_to is None:
        get_m = ctypes.WINFUNCTYPE(
            ctypes.HRESULT, ctypes.c_void_p, ctypes.POINTER(ctypes.c_int)
        )(vtbl[15])  # GetMute
        val = ctypes.c_int()
        if get_m(volume, ctypes.byref(val)) != 0:
            return None
        return bool(val.value)
    set_m = ctypes.WINFUNCTYPE(
        ctypes.HRESULT, ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p
    )(vtbl[14])  # SetMute
    if set_m(volume, 1 if set_to else 0, None) != 0:
        return None
    return bool(set_to)


def audio(*, volume: Optional[Any] = None, mute: Optional[Any] = None) -> Dict[str, Any]:
    if not _win():
        return {"ok": False, "error": "audio is Windows-only"}
    iface = _audio_volume_iface()
    if iface is None:
        return {"ok": False, "error": "default audio endpoint unavailable"}
    try:
        if volume is not None:
            try:
                pct = float(volume)
            except (TypeError, ValueError):
                return {"ok": False, "error": "volume must be 0-100"}
            if pct > 1.0:
                pct = pct / 100.0
            got = _audio_scalar(iface, pct)
            if got is None:
                return {"ok": False, "error": "set volume failed"}
        if mute is not None:
            flag = mute if isinstance(mute, bool) else str(mute).strip().lower() in {
                "1", "true", "yes", "on", "mute",
            }
            got_m = _audio_mute(iface, flag)
            if got_m is None:
                return {"ok": False, "error": "set mute failed"}
        level = _audio_scalar(iface)
        muted = _audio_mute(iface)
        if level is None:
            return {"ok": False, "error": "get volume failed"}
        return {
            "ok": True,
            "volume": int(round(level * 100)),
            "scalar": round(level, 3),
            "muted": bool(muted),
        }
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


# ── brightness ───────────────────────────────────────────────────────

def brightness(*, value: Optional[Any] = None) -> Dict[str, Any]:
    if not _win():
        return {"ok": False, "error": "brightness is Windows-only"}
    try:
        got = _run(
            [
                "powershell", "-NoProfile", "-Command",
                "(Get-CimInstance -Namespace root/wmi -ClassName WmiMonitorBrightness "
                "-ErrorAction SilentlyContinue | Select-Object -First 1).CurrentBrightness",
            ],
            timeout=12,
        )
        raw = (got.stdout or "").strip()
        current = int(raw) if raw.isdigit() else None
    except Exception:
        current = None
    if value is None:
        if current is None:
            return {"ok": False, "error": "no_wmi_brightness", "hint": "desktop displays often have no WMI brightness"}
        return {"ok": True, "brightness": current}
    try:
        pct = int(float(value))
    except (TypeError, ValueError):
        return {"ok": False, "error": "brightness must be 0-100"}
    pct = max(0, min(100, pct))
    try:
        set_out = _run(
            [
                "powershell", "-NoProfile", "-Command",
                f"$m=Get-CimInstance -Namespace root/wmi -ClassName WmiMonitorBrightnessMethods "
                f"-ErrorAction SilentlyContinue | Select-Object -First 1; "
                f"if(-not $m){{'NOMETHOD'; exit 2}}; "
                f"Invoke-CimMethod -InputObject $m -MethodName WmiSetBrightness "
                f"-Arguments @{{Timeout=1; Brightness={pct}}} | Out-Null; 'OK'",
            ],
            timeout=12,
        )
        text = (set_out.stdout or "") + (set_out.stderr or "")
        if "NOMETHOD" in text or set_out.returncode != 0:
            return {"ok": False, "error": "no_wmi_brightness", "brightness": current}
        return {"ok": True, "brightness": pct, "previous": current}
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


# ── network / wifi ───────────────────────────────────────────────────

def network() -> Dict[str, Any]:
    adapters: List[Dict[str, Any]] = []
    if _win():
        try:
            out = _run(["netsh", "interface", "show", "interface"], timeout=10)
            for line in (out.stdout or "").splitlines():
                parts = line.split()
                if len(parts) < 4 or parts[0] in {"Admin", "------"}:
                    continue
                # Admin State  State  Type  Interface Name
                if parts[0] not in {"Enabled", "Disabled"}:
                    continue
                adapters.append({
                    "admin": parts[0].lower(),
                    "state": parts[1].lower() if len(parts) > 1 else "",
                    "name": " ".join(parts[3:]) if len(parts) > 3 else parts[-1],
                })
        except Exception:
            pass
    up = any(a.get("state") == "connected" for a in adapters)
    return {"ok": True, "up": up or None if not adapters else up, "adapters": adapters[:16], "count": len(adapters)}


def wifi() -> Dict[str, Any]:
    if not _win():
        return {"ok": False, "error": "wifi is Windows-only"}
    iface: Dict[str, Any] = {}
    try:
        show = _run(["netsh", "wlan", "show", "interfaces"], timeout=10)
        for line in (show.stdout or "").splitlines():
            if ":" not in line:
                continue
            key, val = line.split(":", 1)
            k = key.strip().lower()
            v = val.strip()
            if k == "ssid" and v and v != "":
                iface["ssid"] = v
            elif k == "state":
                iface["state"] = v.lower()
            elif k == "signal":
                iface["signal"] = v
            elif k == "name" and "name" not in iface:
                iface["interface"] = v
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    profiles: List[str] = []
    try:
        prof = _run(["netsh", "wlan", "show", "profiles"], timeout=10)
        for line in (prof.stdout or "").splitlines():
            if ":" in line and "all user profile" in line.lower():
                profiles.append(line.split(":", 1)[1].strip())
    except Exception:
        pass
    return {
        "ok": True,
        "connected": iface.get("state") == "connected",
        "interface": iface or None,
        "profiles": profiles[:24],
        "profile_count": len(profiles),
    }


def wifi_connect(name: str, *, confirm: bool = False) -> Dict[str, Any]:
    if not _confirm_ok(confirm, kind="wifi_connect"):
        return {"ok": False, "error": "wifi_connect requires confirm=true"}
    ssid = str(name or "").strip()
    if not ssid:
        return {"ok": False, "error": "wifi_connect requires name (saved profile / SSID)"}
    if not _win():
        return {"ok": False, "error": "wifi_connect is Windows-only"}
    try:
        out = _run(["netsh", "wlan", "connect", f"name={ssid}"], timeout=20)
        text = ((out.stdout or "") + (out.stderr or "")).strip()
        ok = out.returncode == 0 and "successfully" in text.lower()
        return {
            "ok": ok,
            "name": ssid,
            "message": text[:240] or None,
            "error": None if ok else (text[:240] or "connect failed"),
        }
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


# ── settings / wallpaper / recycle ───────────────────────────────────

SETTINGS_ALIASES = {
    "display": "ms-settings:display",
    "nightlight": "ms-settings:nightlight",
    "sound": "ms-settings:sound",
    "audio": "ms-settings:sound",
    "network": "ms-settings:network",
    "wifi": "ms-settings:network-wifi",
    "bluetooth": "ms-settings:bluetooth",
    "power": "ms-settings:powersleep",
    "powersleep": "ms-settings:powersleep",
    "about": "ms-settings:about",
    "date": "ms-settings:dateandtime",
    "time": "ms-settings:dateandtime",
    "notifications": "ms-settings:notifications",
    "apps": "ms-settings:appsfeatures",
    "update": "ms-settings:windowsupdate",
    "privacy": "ms-settings:privacy",
    "storage": "ms-settings:storagesense",
}


def settings_open(uri: str = "") -> Dict[str, Any]:
    raw = str(uri or "").strip()
    if not raw:
        raw = "ms-settings:"
    if ":" not in raw:
        raw = SETTINGS_ALIASES.get(raw.lower(), f"ms-settings:{raw}")
    if not raw.lower().startswith("ms-settings:"):
        return {"ok": False, "error": "settings_open only accepts ms-settings: URIs or aliases"}
    if not _win():
        return {"ok": False, "error": "settings_open is Windows-only"}
    try:
        os.startfile(raw)  # type: ignore[attr-defined]
        return {"ok": True, "uri": raw}
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}", "uri": raw}


def wallpaper(*, path: Optional[str] = None, confirm: bool = False) -> Dict[str, Any]:
    if not _win():
        return {"ok": False, "error": "wallpaper is Windows-only"}
    SPI_GETDESKWALLPAPER = 0x0073
    SPI_SETDESKWALLPAPER = 0x0014
    buf = ctypes.create_unicode_buffer(260)
    ctypes.windll.user32.SystemParametersInfoW(SPI_GETDESKWALLPAPER, 260, buf, 0)
    current = buf.value or ""
    if not path:
        return {"ok": True, "path": current or None}
    if not _confirm_ok(confirm, kind="wallpaper"):
        return {"ok": False, "error": "wallpaper set requires confirm=true"}
    from exo_control import files_ops

    ok, resolved, outside = files_ops._resolve_under_roots(path)
    if not ok:
        return {"ok": False, "error": resolved}
    if outside:
        denied = files_ops._outside_denied("wallpaper", resolved, confirm)
        if denied is not None:
            return denied
    p = Path(resolved)
    if not p.is_file():
        return {"ok": False, "error": f"not a file: {p}"}
    SPIF_UPDATEINIFILE = 0x01
    SPIF_SENDCHANGE = 0x02
    done = bool(
        ctypes.windll.user32.SystemParametersInfoW(
            SPI_SETDESKWALLPAPER, 0, str(p), SPIF_UPDATEINIFILE | SPIF_SENDCHANGE
        )
    )
    return {"ok": done, "path": str(p), "previous": current or None} if done else {
        "ok": False, "error": "SystemParametersInfo set wallpaper failed", "path": str(p),
    }


def recycle() -> Dict[str, Any]:
    if not _win():
        return {"ok": False, "error": "recycle is Windows-only"}

    class SHQUERYRBINFO(ctypes.Structure):
        _fields_ = [
            ("cbSize", ctypes.c_ulong),
            ("i64Size", ctypes.c_int64),
            ("i64NumItems", ctypes.c_int64),
        ]

    info = SHQUERYRBINFO()
    info.cbSize = ctypes.sizeof(SHQUERYRBINFO)
    hr = ctypes.windll.shell32.SHQueryRecycleBinW(None, ctypes.byref(info))
    if hr != 0:
        return {"ok": False, "error": f"SHQueryRecycleBin failed hr={hr}"}
    return {
        "ok": True,
        "items": int(info.i64NumItems),
        "bytes": int(info.i64Size),
    }


def recycle_empty(*, confirm: bool = False) -> Dict[str, Any]:
    if not _confirm_ok(confirm, kind="recycle_empty"):
        return {"ok": False, "error": "recycle_empty requires confirm=true"}
    if not _win():
        return {"ok": False, "error": "recycle_empty is Windows-only"}
    SHERB_NOCONFIRMATION = 0x00000001
    SHERB_NOPROGRESSUI = 0x00000002
    SHERB_NOSOUND = 0x00000004
    hr = ctypes.windll.shell32.SHEmptyRecycleBinW(
        None, None, SHERB_NOCONFIRMATION | SHERB_NOPROGRESSUI | SHERB_NOSOUND
    )
    if hr not in (0, 0x8000FFFF):  # S_OK or unexpected empty
        return {"ok": False, "error": f"SHEmptyRecycleBin failed hr={hr}"}
    return {"ok": True, "emptied": True}


# ── packages (winget) ────────────────────────────────────────────────

def package(
    *,
    action: str = "list",
    query: str = "",
    id: Optional[str] = None,
    confirm: bool = False,
    max_items: int = 20,
) -> Dict[str, Any]:
    winget = shutil.which("winget")
    if not winget:
        return {"ok": False, "error": "winget not on PATH"}
    act = str(action or "list").lower()
    if act in {"search", "find"}:
        q = str(query or id or "").strip()
        if not q:
            return {"ok": False, "error": "package search requires query"}
        out = _run(
            [winget, "search", "--query", q, "--accept-source-agreements", "--disable-interactivity"],
            timeout=40,
        )
        lines = [ln.rstrip() for ln in (out.stdout or "").splitlines() if ln.strip()]
        return {
            "ok": out.returncode == 0,
            "action": "search",
            "query": q,
            "lines": lines[: max(4, max_items + 4)],
            "error": None if out.returncode == 0 else ((out.stderr or out.stdout or "search failed")[:240]),
        }
    if act in {"list", "ls", "installed"}:
        args = [winget, "list", "--accept-source-agreements", "--disable-interactivity"]
        q = str(query or id or "").strip()
        if q:
            args.extend(["--name", q])
        out = _run(args, timeout=40)
        lines = [ln.rstrip() for ln in (out.stdout or "").splitlines() if ln.strip()]
        return {
            "ok": out.returncode == 0,
            "action": "list",
            "lines": lines[: max(4, max_items + 4)],
            "error": None if out.returncode == 0 else ((out.stderr or "list failed")[:240]),
        }
    if act in {"install", "add"}:
        if not _confirm_ok(confirm, kind="package_install"):
            return {"ok": False, "error": "package install requires confirm=true"}
        pkg = str(id or query or "").strip()
        if not pkg:
            return {"ok": False, "error": "package install requires id or query"}
        out = _run(
            [
                winget, "install", "--id", pkg, "-e",
                "--accept-package-agreements", "--accept-source-agreements",
                "--disable-interactivity",
            ],
            timeout=180,
        )
        text = ((out.stdout or "") + "\n" + (out.stderr or "")).strip()
        ok = out.returncode == 0
        return {
            "ok": ok,
            "action": "install",
            "id": pkg,
            "message": text[-400:] if text else None,
            "error": None if ok else (text[-240:] or "install failed"),
        }
    return {"ok": False, "error": f"unknown package action: {act}"}


# ── files extras ─────────────────────────────────────────────────────

def files_hash(path: str, *, confirm: bool = False, roots: Optional[Sequence[Path]] = None) -> Dict[str, Any]:
    from exo_control import files_ops

    ok, resolved, outside = files_ops._resolve_under_roots(path, roots)
    if not ok:
        return {"ok": False, "error": resolved}
    if outside:
        denied = files_ops._outside_denied("files_hash", resolved, confirm)
        if denied is not None:
            return denied
    p = Path(resolved)
    if not p.is_file():
        return {"ok": False, "error": f"not a file: {p}"}
    h = hashlib.sha256()
    size = 0
    with p.open("rb") as fh:
        while True:
            chunk = fh.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
            size += len(chunk)
            if size > 256 * 1024 * 1024:
                return {"ok": False, "error": "refusing hash over 256MB"}
    return {"ok": True, "path": str(p), "sha256": h.hexdigest(), "size": size}


def files_touch(path: str, *, confirm: bool = False, roots: Optional[Sequence[Path]] = None) -> Dict[str, Any]:
    from exo_control import files_ops
    from exo_control.trust import is_protected_system_path

    ok, resolved, outside = files_ops._resolve_under_roots(path, roots)
    if not ok:
        return {"ok": False, "error": resolved}
    if is_protected_system_path(resolved):
        return {"ok": False, "error": "protected_system_path", "path": resolved, "denied": True}
    if outside:
        denied = files_ops._outside_denied("files_touch", resolved, confirm)
        if denied is not None:
            return denied
    p = Path(resolved)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.touch()
        return {"ok": True, "path": str(p)}
    except OSError as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def files_zip(
    path: str,
    dest: str = "",
    *,
    confirm: bool = False,
    roots: Optional[Sequence[Path]] = None,
) -> Dict[str, Any]:
    from exo_control import files_ops
    from exo_control.trust import is_protected_system_path

    ok, src, outside = files_ops._resolve_under_roots(path, roots)
    if not ok:
        return {"ok": False, "error": src}
    if is_protected_system_path(src):
        return {"ok": False, "error": "protected_system_path", "path": src, "denied": True}
    if outside:
        denied = files_ops._outside_denied("files_zip", src, confirm)
        if denied is not None:
            return denied
    src_p = Path(src)
    if not src_p.exists():
        return {"ok": False, "error": f"path not found: {src_p}"}
    dest_s = dest or str(src_p.with_suffix(".zip") if src_p.is_file() else src_p.with_name(src_p.name + ".zip"))
    ok, dst, out2 = files_ops._resolve_under_roots(dest_s, roots)
    if not ok:
        return {"ok": False, "error": dst}
    if is_protected_system_path(dst):
        return {"ok": False, "error": "protected_system_path", "path": dst, "denied": True}
    if out2:
        denied = files_ops._outside_denied("files_zip", dst, confirm)
        if denied is not None:
            return denied
    dst_p = Path(dst)
    try:
        if src_p.is_file():
            with zipfile.ZipFile(dst_p, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                zf.write(src_p, arcname=src_p.name)
        else:
            with zipfile.ZipFile(dst_p, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                for file in src_p.rglob("*"):
                    if file.is_file():
                        zf.write(file, arcname=str(file.relative_to(src_p)))
        return {"ok": True, "path": str(src_p), "dest": str(dst_p), "size": dst_p.stat().st_size}
    except OSError as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def files_unzip(
    path: str,
    dest: str = "",
    *,
    confirm: bool = False,
    roots: Optional[Sequence[Path]] = None,
) -> Dict[str, Any]:
    from exo_control import files_ops
    from exo_control.trust import is_protected_system_path

    ok, src, outside = files_ops._resolve_under_roots(path, roots)
    if not ok:
        return {"ok": False, "error": src}
    if outside:
        denied = files_ops._outside_denied("files_unzip", src, confirm)
        if denied is not None:
            return denied
    src_p = Path(src)
    if not src_p.is_file():
        return {"ok": False, "error": f"not a file: {src_p}"}
    dest_s = dest or str(src_p.with_suffix(""))
    ok, dst, out2 = files_ops._resolve_under_roots(dest_s, roots)
    if not ok:
        return {"ok": False, "error": dst}
    if is_protected_system_path(dst):
        return {"ok": False, "error": "protected_system_path", "path": dst, "denied": True}
    if out2:
        denied = files_ops._outside_denied("files_unzip", dst, confirm)
        if denied is not None:
            return denied
    dst_p = Path(dst)
    try:
        dst_p.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(src_p, "r") as zf:
            # Zip-slip guard
            for info in zf.infolist():
                target = (dst_p / info.filename).resolve()
                target.relative_to(dst_p.resolve())
            zf.extractall(dst_p)
            count = len(zf.namelist())
        return {"ok": True, "path": str(src_p), "dest": str(dst_p), "count": count}
    except (OSError, zipfile.BadZipFile, ValueError) as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def files_reveal(path: str, *, confirm: bool = False, roots: Optional[Sequence[Path]] = None) -> Dict[str, Any]:
    from exo_control import files_ops

    ok, resolved, outside = files_ops._resolve_under_roots(path, roots)
    if not ok:
        return {"ok": False, "error": resolved}
    if outside:
        denied = files_ops._outside_denied("files_reveal", resolved, confirm)
        if denied is not None:
            return denied
    p = Path(resolved)
    if not p.exists():
        return {"ok": False, "error": f"path not found: {p}"}
    if not _win():
        return {"ok": False, "error": "files_reveal is Windows-only"}
    try:
        if p.is_dir():
            os.startfile(str(p))  # type: ignore[attr-defined]
        else:
            _run(["explorer", f"/select,{p}"], timeout=8)
        return {"ok": True, "path": str(p)}
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


# ── watch ────────────────────────────────────────────────────────────

def watch_file(
    path: str,
    *,
    state: str = "exists",
    timeout: float = 15.0,
    poll: float = 0.25,
    confirm: bool = False,
    roots: Optional[Sequence[Path]] = None,
) -> Dict[str, Any]:
    from exo_control import files_ops

    ok, resolved, outside = files_ops._resolve_under_roots(path, roots)
    if not ok:
        return {"ok": False, "error": resolved}
    if outside:
        denied = files_ops._outside_denied("watch_file", resolved, confirm)
        if denied is not None:
            return denied
    p = Path(resolved)
    want = str(state or "exists").lower()
    timeout = max(0.2, min(120.0, float(timeout)))
    poll = max(0.05, float(poll))
    started = time.perf_counter()
    first_mtime = p.stat().st_mtime if p.exists() else None
    while True:
        exists = p.exists()
        if want in {"exists", "create", "created", "appear"} and exists:
            return {"ok": True, "path": str(p), "state": "exists", "waited": round(time.perf_counter() - started, 3)}
        if want in {"gone", "delete", "deleted", "missing"} and not exists:
            return {"ok": True, "path": str(p), "state": "gone", "waited": round(time.perf_counter() - started, 3)}
        if want in {"change", "changed", "mtime"} and exists:
            try:
                mt = p.stat().st_mtime
            except OSError:
                mt = None
            if first_mtime is None and mt is not None:
                first_mtime = mt
            elif mt is not None and first_mtime is not None and mt != first_mtime:
                return {"ok": True, "path": str(p), "state": "changed", "waited": round(time.perf_counter() - started, 3)}
        if time.perf_counter() - started >= timeout:
            return {
                "ok": False,
                "error": f"watch_file timeout after {timeout}s (wanted {want})",
                "path": str(p),
                "exists": exists,
                "timeout": timeout,
            }
        time.sleep(min(poll, max(0.05, timeout - (time.perf_counter() - started))))


def watch_proc(
    name: str = "",
    *,
    pid: Optional[int] = None,
    state: str = "running",
    timeout: float = 15.0,
    poll: float = 0.3,
) -> Dict[str, Any]:
    from exo_control import infra_ops

    want = str(state or "running").lower()
    timeout = max(0.2, min(120.0, float(timeout)))
    poll = max(0.05, float(poll))
    started = time.perf_counter()
    needle = str(name or "").strip()

    def present() -> bool:
        if pid is not None:
            return bool(infra_ops._proc_name_for_pid(int(pid)))
        if not needle:
            return False
        return bool(infra_ops.find_pids_by_name(needle, max_hits=1))

    while True:
        here = present()
        if want in {"running", "start", "started", "appear"} and here:
            return {"ok": True, "state": "running", "name": needle or None, "pid": pid, "waited": round(time.perf_counter() - started, 3)}
        if want in {"gone", "exit", "exited", "stop", "stopped"} and not here:
            return {"ok": True, "state": "gone", "name": needle or None, "pid": pid, "waited": round(time.perf_counter() - started, 3)}
        if time.perf_counter() - started >= timeout:
            return {
                "ok": False,
                "error": f"watch_proc timeout after {timeout}s (wanted {want})",
                "name": needle or None,
                "pid": pid,
                "present": here,
                "timeout": timeout,
            }
        time.sleep(min(poll, max(0.05, timeout - (time.perf_counter() - started))))


# ── find (UI text → refs) ────────────────────────────────────────────

def match_elements(elements: Sequence[Dict[str, Any]], query: str, *, max_items: int = 20) -> Dict[str, Any]:
    q = str(query or "").strip().lower()
    if not q:
        return {"ok": False, "error": "find requires query"}
    hits: List[Dict[str, Any]] = []
    for el in elements:
        if not isinstance(el, dict):
            continue
        name = str(el.get("name") or el.get("label") or "")
        role = str(el.get("role") or "")
        blob = f"{name} {role}".lower()
        if q not in blob:
            continue
        hits.append({
            "ref": el.get("ref"),
            "name": name,
            "role": role or None,
            "element_index": el.get("element_index"),
            "bbox": el.get("bbox"),
        })
        if len(hits) >= max_items:
            break
    return {"ok": True, "query": query, "matches": hits, "count": len(hits), "capped": len(hits) >= max_items}


# ── snapshot ─────────────────────────────────────────────────────────

def status() -> Dict[str, Any]:
    out: Dict[str, Any] = {"ok": True, "clock": clock()}
    for key, fn in (
        ("idle", idle),
        ("power", power),
        ("audio", audio),
        ("network", network),
        ("wifi", wifi),
        ("recycle", recycle),
    ):
        try:
            out[key] = fn()
        except Exception as exc:
            out[key] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    return out


def dispatch(action: str, step: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Router for op=pc action=… plus first-class names."""
    from exo_control.policy import parse_confirm

    step = dict(step or {})
    act = str(action or step.get("action") or "status").strip().lower()
    confirm = parse_confirm(step.get("confirm", False))
    if act in {"status", "snapshot", "pc"}:
        return status()
    if act in {"audio", "volume"}:
        return audio(volume=step.get("volume") if "volume" in step else step.get("value"), mute=step.get("mute"))
    if act == "mute":
        return audio(mute=True if step.get("mute") is None else step.get("mute"))
    if act == "brightness":
        return brightness(value=step.get("value") if "value" in step else step.get("brightness"))
    if act in {"power", "battery"}:
        return power()
    if act == "lock":
        return lock()
    if act == "sleep":
        return sleep(confirm=confirm)
    if act == "idle":
        return idle()
    if act == "clock":
        return clock()
    if act == "network":
        return network()
    if act == "wifi":
        return wifi()
    if act == "wifi_connect":
        return wifi_connect(str(step.get("name") or step.get("ssid") or ""), confirm=confirm)
    if act in {"settings_open", "ms_settings", "settings"}:
        return settings_open(str(step.get("uri") or step.get("url") or step.get("page") or step.get("name") or ""))
    if act == "wallpaper":
        return wallpaper(path=step.get("path"), confirm=confirm)
    if act == "recycle":
        return recycle()
    if act == "recycle_empty":
        return recycle_empty(confirm=confirm)
    if act in {"package", "winget"}:
        return package(
            action=str(step.get("action") or step.get("mode") or "list"),
            query=str(step.get("query") or step.get("q") or ""),
            id=step.get("id") or step.get("package"),
            confirm=confirm,
            max_items=int(step.get("max", 20)),
        )
    if act == "files_hash":
        return files_hash(str(step.get("path") or ""), confirm=confirm)
    if act == "files_touch":
        return files_touch(str(step.get("path") or ""), confirm=confirm)
    if act == "files_zip":
        return files_zip(str(step.get("path") or ""), str(step.get("dest") or step.get("to") or ""), confirm=confirm)
    if act == "files_unzip":
        return files_unzip(str(step.get("path") or ""), str(step.get("dest") or step.get("to") or ""), confirm=confirm)
    if act == "files_reveal":
        return files_reveal(str(step.get("path") or ""), confirm=confirm)
    if act == "watch_file":
        return watch_file(
            str(step.get("path") or ""),
            state=str(step.get("state") or step.get("want") or "exists"),
            timeout=float(step.get("timeout", 15.0)),
            poll=float(step.get("poll", 0.25)),
            confirm=confirm,
        )
    if act == "watch_proc":
        pid = step.get("pid")
        return watch_proc(
            str(step.get("name") or step.get("process") or ""),
            pid=int(pid) if pid is not None else None,
            state=str(step.get("state") or step.get("want") or "running"),
            timeout=float(step.get("timeout", 15.0)),
            poll=float(step.get("poll", 0.3)),
        )
    return {"ok": False, "error": f"unknown pc action: {act}"}
