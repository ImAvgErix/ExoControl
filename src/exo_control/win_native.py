"""Stock Windows natives — ctypes / netsh / PowerShell / COM. No extra pip.

Linux CI never enters these paths. Tests replace ``_RUN`` or the per-op functions.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Sequence

from exo_control.http_json import clip_int, truncate

_RUN = None


def run(args: Sequence[str], timeout: float = 20.0) -> subprocess.CompletedProcess:
    if _RUN is not None:
        return _RUN(list(args), timeout)
    return subprocess.run(list(args), capture_output=True, text=True, timeout=timeout, check=False)


def powershell(script: str, timeout: float = 25.0) -> subprocess.CompletedProcess:
    return run(
        ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", script],
        timeout,
    )


def parse_netsh_wlan(text: str) -> Dict[str, Any]:
    ssid = ""
    state = ""
    signal = ""
    name = ""
    for line in (text or "").splitlines():
        if ":" not in line:
            continue
        key, val = line.split(":", 1)
        key = key.strip().lower()
        val = val.strip()
        if key == "ssid":
            ssid = val
        elif key == "state":
            state = val
        elif key == "signal":
            signal = val
        elif key == "name":
            name = val
    return {
        "ok": True,
        "provider": "netsh",
        "ssid": ssid,
        "state": state,
        "signal": signal,
        "interface": name,
        "connected": state.lower() == "connected",
    }


def parse_netstat_listening(text: str) -> Dict[str, Any]:
    rows: List[Dict[str, Any]] = []
    for line in (text or "").splitlines():
        parts = line.split()
        if len(parts) < 4:
            continue
        proto = parts[0].upper()
        if proto not in {"TCP", "UDP"}:
            continue
        local = parts[1]
        state = parts[3].upper() if proto == "TCP" and len(parts) >= 4 else "LISTEN"
        if proto == "TCP" and state != "LISTENING":
            continue
        host, _, port_s = local.rpartition(":")
        try:
            port = int(port_s)
        except ValueError:
            continue
        pid = None
        if parts[-1].isdigit():
            pid = int(parts[-1])
        rows.append({"proto": proto.lower(), "port": port, "addr": host, "pid": pid})
        if len(rows) >= 40:
            break
    return {"ok": True, "listeners": rows, "count": len(rows)}


def _fail(op: str, exc: Exception) -> Dict[str, Any]:
    return {"ok": False, "error": f"{type(exc).__name__}: {exc}", "code": "UNAVAILABLE", "op": op}


def volume(step: Dict[str, Any]) -> Dict[str, Any]:
    try:
        return _volume_endpoint(step)
    except Exception as exc:
        return _fail("volume", exc)


def _volume_endpoint(step: Dict[str, Any]) -> Dict[str, Any]:
    import ctypes
    from ctypes import HRESULT, POINTER, byref, c_float, c_int, c_void_p, c_wchar_p

    ole32 = ctypes.OleDLL("ole32")
    ole32.CoInitialize(None)

    class GUID(ctypes.Structure):
        _fields_ = [
            ("Data1", ctypes.c_uint32),
            ("Data2", ctypes.c_uint16),
            ("Data3", ctypes.c_uint16),
            ("Data4", ctypes.c_ubyte * 8),
        ]

    def guid(text: str) -> GUID:
        g = GUID()
        ole32.CLSIDFromString(ctypes.c_wchar_p(text), byref(g))
        return g

    class IUnknown(ctypes.Structure):
        pass

    # Use PowerShell one-file that works: Windows 10+ has System.Windows.Forms SendKeys — not volume.
    # Implement IMMDeviceEnumerator via known vtable offsets (widely copied, stock ole32).
    enumerator_clsid = guid("{BCDE0395-E52F-467C-8E3D-C4579291692E}")
    enumerator_iid = guid("{A95664D2-9614-4F35-A746-DE8DB63617E6}")
    volume_iid = guid("{5CDF2C82-841E-4546-9722-0CF74078229A}")

    enumerator = c_void_p()
    hr = ole32.CoCreateInstance(
        byref(enumerator_clsid), None, 23, byref(enumerator_iid), byref(enumerator)
    )
    if hr != 0 or not enumerator.value:
        raise OSError(f"CoCreateInstance MMDeviceEnumerator hr={hr}")

    # vtable: QueryInterface, AddRef, Release, EnumAudioEndpoints, GetDefaultAudioEndpoint
    vtbl = ctypes.cast(enumerator, POINTER(c_void_p))[0]
    fns = ctypes.cast(vtbl, POINTER(c_void_p))

    GetDefaultAudioEndpoint = ctypes.WINFUNCTYPE(
        HRESULT, c_void_p, c_int, c_int, POINTER(c_void_p)
    )(fns[4])
    device = c_void_p()
    hr = GetDefaultAudioEndpoint(enumerator, 0, 1, byref(device))  # eRender, eMultimedia
    if hr != 0:
        raise OSError(f"GetDefaultAudioEndpoint hr={hr}")

    Activate = ctypes.WINFUNCTYPE(
        HRESULT, c_void_p, POINTER(GUID), ctypes.c_uint32, c_void_p, POINTER(c_void_p)
    )(ctypes.cast(ctypes.cast(device, POINTER(c_void_p))[0], POINTER(c_void_p))[3])
    endpoint = c_void_p()
    hr = Activate(device, byref(volume_iid), 23, None, byref(endpoint))
    if hr != 0:
        raise OSError(f"Activate IAudioEndpointVolume hr={hr}")

    evtbl = ctypes.cast(ctypes.cast(endpoint, POINTER(c_void_p))[0], POINTER(c_void_p))
    SetMasterVolumeLevelScalar = ctypes.WINFUNCTYPE(
        HRESULT, c_void_p, c_float, c_void_p
    )(evtbl[7])
    GetMasterVolumeLevelScalar = ctypes.WINFUNCTYPE(
        HRESULT, c_void_p, POINTER(c_float)
    )(evtbl[9])
    SetMute = ctypes.WINFUNCTYPE(HRESULT, c_void_p, c_int, c_void_p)(evtbl[14])
    GetMute = ctypes.WINFUNCTYPE(HRESULT, c_void_p, POINTER(c_int))(evtbl[15])

    if step.get("level") is not None:
        level = max(0, min(100, int(step["level"])))
        SetMasterVolumeLevelScalar(endpoint, c_float(level / 100.0), None)
    action = str(step.get("action") or "").lower()
    if step.get("mute") is True or action == "mute":
        SetMute(endpoint, 1, None)
    if step.get("mute") is False or action == "unmute":
        SetMute(endpoint, 0, None)
    scalar = c_float()
    GetMasterVolumeLevelScalar(endpoint, byref(scalar))
    muted = c_int()
    GetMute(endpoint, byref(muted))
    return {
        "ok": True,
        "native": True,
        "level": int(round(float(scalar.value) * 100)),
        "muted": bool(muted.value),
    }


def recycle(step: Dict[str, Any]) -> Dict[str, Any]:
    action = str(step.get("action") or "list").lower()
    if action in {"empty", "clear", "wipe"}:
        proc = powershell(
            "Clear-RecycleBin -Force -ErrorAction SilentlyContinue; 'emptied'",
            timeout=30,
        )
        return {
            "ok": proc.returncode == 0,
            "native": True,
            "emptied": proc.returncode == 0,
            "error": None if proc.returncode == 0 else truncate((proc.stderr or "recycle empty failed").strip(), 300),
        }
    proc = powershell(
        "(New-Object -ComObject Shell.Application).NameSpace(10).Items() | "
        "Select-Object -First 20 -ExpandProperty Name",
        timeout=20,
    )
    names = [ln.strip() for ln in (proc.stdout or "").splitlines() if ln.strip()]
    return {"ok": True, "native": True, "items": [{"name": n} for n in names], "count": len(names)}


def tts(step: Dict[str, Any]) -> Dict[str, Any]:
    text = str(step.get("text") or step.get("say") or "").replace("'", "''")
    if not text.strip():
        return {"ok": False, "error": "tts requires text", "code": "MISSING_TEXT"}
    proc = powershell(
        "Add-Type -AssemblyName System.Speech; "
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        f"$s.Speak('{text[:400]}')",
        timeout=40,
    )
    if proc.returncode != 0:
        return {"ok": False, "error": truncate((proc.stderr or "tts failed").strip(), 300), "code": "UNAVAILABLE"}
    return {"ok": True, "native": True, "spoke": True}


def ocr_win(step: Dict[str, Any]) -> Dict[str, Any]:
    path = str(step.get("path") or step.get("image") or "").replace("'", "''")
    if not path:
        return {"ok": False, "error": "ocr_win requires path", "code": "MISSING_PATH"}
    proc = powershell(
        f"$p = '{path}'; "
        "Add-Type -AssemblyName System.Runtime.WindowsRuntime -ErrorAction SilentlyContinue; "
        "$null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType=WindowsRuntime]; "
        "try { "
        "$eng = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages(); "
        "if (-not $eng) { 'OCR_UNAVAILABLE'; exit 2 }; "
        "'OCR_UNAVAILABLE' "
        "} catch { 'OCR_UNAVAILABLE' }",
        timeout=20,
    )
    text = (proc.stdout or "").strip()
    if "OCR_UNAVAILABLE" in text or proc.returncode != 0:
        return {
            "ok": False,
            "error": "WinRT OCR not bound; use omni or files_convert",
            "code": "UNAVAILABLE",
            "hint": "Install desktop OCR language pack, or call omni / files_convert",
        }
    return {"ok": True, "native": True, "text": truncate(text, 2000)}


def stt(step: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "ok": False,
        "error": "stt has no stock Windows API we will pretend works",
        "code": "UNAVAILABLE",
        "hint": "Use a real STT key path later; do not invent transcripts",
    }


def wifi(step: Dict[str, Any]) -> Dict[str, Any]:
    proc = run(["netsh", "wlan", "show", "interfaces"], timeout=15)
    if proc.returncode != 0:
        return {"ok": False, "error": truncate((proc.stderr or "netsh failed").strip(), 300), "code": "UNAVAILABLE"}
    out = parse_netsh_wlan(proc.stdout or "")
    out["native"] = True
    return out


def power(step: Dict[str, Any]) -> Dict[str, Any]:
    action = str(step.get("action") or "status").lower()
    if action in {"sleep", "suspend"}:
        proc = run(["rundll32", "powrprof.dll,SetSuspendState", "0,1,0"], timeout=10)
        return {"ok": proc.returncode == 0, "native": True, "action": "sleep"}
    if action == "hibernate":
        proc = run(["shutdown", "/h"], timeout=10)
        return {"ok": proc.returncode == 0, "native": True, "action": "hibernate"}
    if action == "shutdown":
        return {"ok": False, "error": "power shutdown is denied (use the Start menu)", "code": "DENIED"}
    try:
        import ctypes
        from ctypes import wintypes

        class SYSTEM_POWER_STATUS(ctypes.Structure):
            _fields_ = [
                ("ACLineStatus", ctypes.c_byte),
                ("BatteryFlag", ctypes.c_byte),
                ("BatteryLifePercent", ctypes.c_byte),
                ("SystemStatusFlag", ctypes.c_byte),
                ("BatteryLifeTime", wintypes.DWORD),
                ("BatteryFullLifeTime", wintypes.DWORD),
            ]

        st = SYSTEM_POWER_STATUS()
        if ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(st)) == 0:
            raise OSError("GetSystemPowerStatus failed")
        pct = int(st.BatteryLifePercent)
        return {
            "ok": True,
            "native": True,
            "plugged": st.ACLineStatus == 1,
            "percent": pct if 0 <= pct <= 100 else None,
            "action": "status",
        }
    except Exception as exc:
        return _fail("power", exc)


def print_file(step: Dict[str, Any]) -> Dict[str, Any]:
    path = str(step.get("path") or step.get("file") or "")
    try:
        os.startfile(path, "print")  # type: ignore[attr-defined]
        return {"ok": True, "native": True, "printed": True, "path": path}
    except Exception as exc:
        return _fail("print", exc)


def dialog(step: Dict[str, Any]) -> Dict[str, Any]:
    text = str(step.get("text") or step.get("message") or "")
    title = str(step.get("title") or "Exo Control")
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, text[:1000], title[:120], 0x00000040)
        return {"ok": True, "native": True, "shown": True}
    except Exception as exc:
        return _fail("dialog", exc)


def lnk(step: Dict[str, Any]) -> Dict[str, Any]:
    path = str(step.get("path") or "").replace("'", "''")
    target = str(step.get("target") or step.get("dest") or "").replace("'", "''")
    if target:
        if not path:
            return {"ok": False, "error": "lnk create requires path", "code": "MISSING_PATH"}
        proc = powershell(
            "$w = New-Object -ComObject WScript.Shell; "
            f"$s = $w.CreateShortcut('{path}'); "
            f"$s.TargetPath = '{target}'; $s.Save(); 'created'",
            timeout=15,
        )
        return {
            "ok": proc.returncode == 0,
            "native": True,
            "created": proc.returncode == 0,
            "path": path,
            "target": target,
        }
    if not path:
        return {"ok": False, "error": "lnk requires path", "code": "MISSING_PATH"}
    proc = powershell(
        "$w = New-Object -ComObject WScript.Shell; "
        f"$s = $w.CreateShortcut('{path}'); $s.TargetPath",
        timeout=15,
    )
    target_out = (proc.stdout or "").strip()
    if proc.returncode != 0 or not target_out:
        return {"ok": False, "error": "could not read shortcut", "code": "UNAVAILABLE"}
    return {"ok": True, "native": True, "path": path, "target": target_out}


def certs(step: Dict[str, Any]) -> Dict[str, Any]:
    proc = run(["certutil", "-store", "-user", "My"], timeout=20)
    rows = []
    subject = None
    for line in (proc.stdout or "").splitlines():
        if "Subject:" in line or line.strip().startswith("CN="):
            subject = line.split(":", 1)[-1].strip()
            rows.append({"subject": subject})
        if len(rows) >= 15:
            break
    return {"ok": True, "native": True, "certs": rows, "count": len(rows)}


def winsearch(step: Dict[str, Any]) -> Dict[str, Any]:
    query = str(step.get("query") or "").replace("'", "''")
    top = clip_int(step.get("max") or 15, 15, 1, 40)
    root = (os.environ.get("USERPROFILE") or os.environ.get("HOME") or ".").replace("'", "''")
    proc = powershell(
        f"Get-ChildItem -LiteralPath '{root}' -Recurse -File -ErrorAction SilentlyContinue | "
        f"Where-Object {{ $_.Name -like '*{query}*' }} | Select-Object -First {top} FullName, Name | "
        "ForEach-Object { $_.Name + '|' + $_.FullName }",
        timeout=25,
    )
    hits = []
    for line in (proc.stdout or "").splitlines():
        if "|" not in line:
            continue
        name, full = line.split("|", 1)
        hits.append({"name": name.strip(), "path": full.strip()})
    return {"ok": True, "native": True, "hits": hits, "count": len(hits), "provider": "walk"}


def lock_pc(step: Dict[str, Any]) -> Dict[str, Any]:
    try:
        import ctypes
        ok = bool(ctypes.windll.user32.LockWorkStation())
        return {"ok": ok, "native": True, "locked": ok}
    except Exception as exc:
        return _fail("lock_pc", exc)


def idle(step: Dict[str, Any]) -> Dict[str, Any]:
    try:
        import ctypes
        from ctypes import wintypes

        class LASTINPUTINFO(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]

        info = LASTINPUTINFO()
        info.cbSize = ctypes.sizeof(LASTINPUTINFO)
        if ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)) == 0:
            raise OSError("GetLastInputInfo failed")
        ticks = ctypes.windll.kernel32.GetTickCount()
        seconds = max(0.0, (int(ticks) - int(info.dwTime)) / 1000.0)
        return {"ok": True, "native": True, "seconds": round(seconds, 2)}
    except Exception as exc:
        return _fail("idle", exc)


def brightness(step: Dict[str, Any]) -> Dict[str, Any]:
    proc = powershell(
        "Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightness -ErrorAction SilentlyContinue | "
        "Select-Object -First 1 -ExpandProperty CurrentBrightness",
        timeout=15,
    )
    raw = (proc.stdout or "").strip()
    try:
        level = int(raw)
    except ValueError:
        return {"ok": False, "error": "brightness WMI unavailable", "code": "UNAVAILABLE"}
    return {"ok": True, "native": True, "level": level}


def dark_mode(step: Dict[str, Any]) -> Dict[str, Any]:
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
        )
        val, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
        winreg.CloseKey(key)
        return {"ok": True, "native": True, "dark": int(val) == 0, "apps_use_light": int(val) == 1}
    except Exception as exc:
        return _fail("dark_mode", exc)


def ports(step: Dict[str, Any]) -> Dict[str, Any]:
    proc = run(["netstat", "-ano"], timeout=15)
    if proc.returncode != 0:
        return {"ok": False, "error": "netstat failed", "code": "UNAVAILABLE"}
    out = parse_netstat_listening(proc.stdout or "")
    out["native"] = True
    return out


def uptime(step: Dict[str, Any]) -> Dict[str, Any]:
    try:
        import ctypes
        ticks = ctypes.windll.kernel32.GetTickCount64()
        return {"ok": True, "native": True, "seconds": int(ticks) / 1000.0}
    except Exception as exc:
        return _fail("uptime", exc)


def usb(step: Dict[str, Any]) -> Dict[str, Any]:
    proc = powershell(
        "Get-PnpDevice -Class USB -Status OK -ErrorAction SilentlyContinue | "
        "Select-Object -First 20 FriendlyName | ForEach-Object { $_.FriendlyName }",
        timeout=20,
    )
    names = [ln.strip() for ln in (proc.stdout or "").splitlines() if ln.strip()]
    return {"ok": True, "native": True, "devices": names, "count": len(names)}


def bluetooth(step: Dict[str, Any]) -> Dict[str, Any]:
    proc = powershell(
        "Get-PnpDevice -Class Bluetooth -ErrorAction SilentlyContinue | "
        "Select-Object -First 20 FriendlyName, Status | "
        "ForEach-Object { $_.Status + '|' + $_.FriendlyName }",
        timeout=20,
    )
    devices = []
    for line in (proc.stdout or "").splitlines():
        if "|" not in line:
            continue
        status, name = line.split("|", 1)
        devices.append({"name": name.strip(), "status": status.strip()})
    return {"ok": True, "native": True, "devices": devices, "count": len(devices)}


def printers(step: Dict[str, Any]) -> Dict[str, Any]:
    proc = powershell(
        "Get-Printer -ErrorAction SilentlyContinue | Select-Object -First 20 Name | ForEach-Object { $_.Name }",
        timeout=15,
    )
    names = [ln.strip() for ln in (proc.stdout or "").splitlines() if ln.strip()]
    return {"ok": True, "native": True, "printers": names, "count": len(names)}


def bitlocker(step: Dict[str, Any]) -> Dict[str, Any]:
    exe = "manage-bde"
    proc = run([exe, "-status"], timeout=20)
    text = truncate((proc.stdout or proc.stderr or "").strip(), 2500)
    return {
        "ok": proc.returncode == 0,
        "native": True,
        "text": text,
        "error": None if proc.returncode == 0 else "manage-bde failed",
    }


def defender(step: Dict[str, Any]) -> Dict[str, Any]:
    proc = powershell(
        "Get-MpComputerStatus -ErrorAction SilentlyContinue | "
        "Select-Object AMServiceEnabled, AntivirusEnabled, RealTimeProtectionEnabled, "
        "IoavProtectionEnabled, NISEnabled | ConvertTo-Json -Compress",
        timeout=20,
    )
    raw = (proc.stdout or "").strip()
    if not raw:
        return {"ok": False, "error": "Defender status unavailable", "code": "UNAVAILABLE"}
    import json
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {"ok": True, "native": True, "text": truncate(raw, 800)}
    return {"ok": True, "native": True, "status": parsed}


def win_updates(step: Dict[str, Any]) -> Dict[str, Any]:
    proc = powershell(
        "Get-HotFix -ErrorAction SilentlyContinue | Sort-Object InstalledOn -Descending | "
        "Select-Object -First 8 HotFixID, Description, InstalledOn | "
        "ForEach-Object { $_.HotFixID + '|' + $_.Description }",
        timeout=25,
    )
    items = []
    for line in (proc.stdout or "").splitlines():
        if "|" not in line:
            continue
        hid, desc = line.split("|", 1)
        items.append({"id": hid.strip(), "description": desc.strip()})
    return {"ok": True, "native": True, "updates": items, "count": len(items)}


def fonts(step: Dict[str, Any]) -> Dict[str, Any]:
    root = Path(os.environ.get("WINDIR") or r"C:\Windows") / "Fonts"
    if not root.is_dir():
        return {"ok": False, "error": "Fonts folder missing", "code": "UNAVAILABLE"}
    names = sorted(p.name for p in root.iterdir() if p.is_file())[:40]
    return {"ok": True, "native": True, "fonts": names, "count": len(names), "path": str(root)}


WINDOWS_NATIVE_OPS = (
    "volume", "recycle", "tts", "ocr_win", "wifi", "power", "print", "dialog",
    "lnk", "certs", "winsearch", "lock_pc", "idle", "brightness", "dark_mode",
    "ports", "uptime", "usb", "bluetooth", "printers", "bitlocker", "defender",
    "win_updates", "fonts", "winget", "eventlog",
)
