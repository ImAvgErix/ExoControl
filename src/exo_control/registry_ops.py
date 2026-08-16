"""Windows registry ops for Exo Control (winreg)."""
from __future__ import annotations

import sys
from typing import Any, Dict, List, Optional, Tuple

_HIVE_MAP = {
    "HKCU": "HKEY_CURRENT_USER",
    "HKEY_CURRENT_USER": "HKEY_CURRENT_USER",
    "HKLM": "HKEY_LOCAL_MACHINE",
    "HKEY_LOCAL_MACHINE": "HKEY_LOCAL_MACHINE",
    "HKCR": "HKEY_CLASSES_ROOT",
    "HKEY_CLASSES_ROOT": "HKEY_CLASSES_ROOT",
    "HKU": "HKEY_USERS",
    "HKEY_USERS": "HKEY_USERS",
}


def _parse_path(path: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    raw = (path or "").strip().strip("\\/")
    if not raw:
        return None, None, "empty registry path"
    parts = raw.replace("/", "\\").split("\\")
    hive_token = parts[0].upper()
    # normalize common casing
    for k in _HIVE_MAP:
        if hive_token == k.upper():
            hive_name = _HIVE_MAP[k]
            break
    else:
        return None, None, f"unknown hive: {parts[0]}"
    key = "\\".join(parts[1:]) if len(parts) > 1 else ""
    return hive_name, key, None


def _winreg():
    if sys.platform != "win32":
        return None
    import winreg  # type: ignore
    return winreg


def _type_name(winreg, typ: int) -> str:
    mapping = {
        winreg.REG_SZ: "string",
        winreg.REG_EXPAND_SZ: "expand_sz",
        winreg.REG_DWORD: "dword",
        getattr(winreg, "REG_QWORD", 11): "qword",
        winreg.REG_BINARY: "binary",
        winreg.REG_MULTI_SZ: "multi_sz",
    }
    return mapping.get(typ, str(typ))


def registry_read(path: str, max_values: int = 40) -> Dict[str, Any]:
    winreg = _winreg()
    if winreg is None:
        return {"ok": False, "error": "registry ops require Windows"}
    hive_name, key, err = _parse_path(path)
    if err:
        return {"ok": False, "error": err}
    hive = getattr(winreg, hive_name)
    try:
        handle = winreg.OpenKey(hive, key or "", 0, winreg.KEY_READ)
    except FileNotFoundError:
        return {"ok": False, "error": "key not found", "hive": hive_name, "key": key}
    except OSError as exc:
        return {"ok": False, "error": f"open failed: {exc}", "hive": hive_name, "key": key}
    values: List[Dict[str, Any]] = []
    try:
        i = 0
        while len(values) < max_values:
            try:
                name, data, typ = winreg.EnumValue(handle, i)
            except OSError:
                break
            i += 1
            tname = _type_name(winreg, typ)
            if isinstance(data, bytes):
                rendered: Any = data[:64].hex()
            elif isinstance(data, list):
                rendered = data[:20]
            else:
                rendered = data
                if isinstance(rendered, str) and len(rendered) > 500:
                    rendered = rendered[:497] + "..."
            values.append({"name": name, "type": tname, "value": rendered})
        return {
            "ok": True,
            "hive": hive_name,
            "key": key,
            "values": values,
            "count": len(values),
            "capped": len(values) >= max_values,
        }
    finally:
        try:
            winreg.CloseKey(handle)
        except Exception:
            pass


def _hive_write_allowed(hive_name: str) -> bool:
    if hive_name == "HKEY_CURRENT_USER":
        return True
    from exo_control.trust import unrestricted

    return unrestricted()


def registry_write(
    path: str,
    name: str,
    value: Any,
    *,
    value_type: str = "string",
    confirm: bool = False,
) -> Dict[str, Any]:
    winreg = _winreg()
    if winreg is None:
        return {"ok": False, "error": "registry ops require Windows"}
    hive_name, key, err = _parse_path(path)
    if err:
        return {"ok": False, "error": err}
    if not _hive_write_allowed(hive_name):
        return {
            "ok": False,
            "error": f"{hive_name} write denied (default/trusted). Full-Trust owner mode required.",
            "hive": hive_name,
            "key": key,
        }
    from exo_control.policy import confirm_ok

    kind = "hklm" if hive_name == "HKEY_LOCAL_MACHINE" else "registry_write"
    if not confirm_ok(confirm, kind=kind):
        return {"ok": False, "error": "registry_write requires confirm=true", "hive": hive_name, "key": key}
    hive = getattr(winreg, hive_name)
    typ_map = {
        "string": winreg.REG_SZ,
        "sz": winreg.REG_SZ,
        "reg_sz": winreg.REG_SZ,
        "expand_sz": winreg.REG_EXPAND_SZ,
        "reg_expand_sz": winreg.REG_EXPAND_SZ,
        "dword": winreg.REG_DWORD,
        "reg_dword": winreg.REG_DWORD,
    }
    typ = typ_map.get((value_type or "string").lower())
    if typ is None:
        return {"ok": False, "error": f"unsupported type: {value_type}"}
    data: Any = value
    if typ == winreg.REG_DWORD:
        try:
            data = int(value)
        except (TypeError, ValueError):
            return {"ok": False, "error": "dword value must be int"}
    else:
        data = str(value)
    try:
        handle = winreg.CreateKeyEx(hive, key or "", 0, winreg.KEY_WRITE)
        try:
            winreg.SetValueEx(handle, str(name), 0, typ, data)
        finally:
            winreg.CloseKey(handle)
        return {
            "ok": True,
            "hive": hive_name,
            "key": key,
            "name": str(name),
            "type": (value_type or "string").lower(),
            "value": data,
        }
    except OSError as exc:
        failed = {"ok": False, "error": f"write failed: {exc}", "hive": hive_name, "key": key}
        from exo_control.elevate import retry_if_needed

        return retry_if_needed(
            "registry_write",
            failed,
            {"path": path, "name": name, "value": value, "value_type": value_type},
        )


def registry_delete(
    path: str,
    name: Optional[str] = None,
    *,
    recursive: bool = False,
    confirm: bool = False,
) -> Dict[str, Any]:
    """Delete a value (when ``name``) or a key."""
    winreg = _winreg()
    if winreg is None:
        return {"ok": False, "error": "registry ops require Windows"}
    hive_name, key, err = _parse_path(path)
    if err:
        return {"ok": False, "error": err}
    if not _hive_write_allowed(hive_name):
        return {
            "ok": False,
            "error": f"{hive_name} delete denied (default/trusted). Full-Trust owner mode required.",
            "hive": hive_name,
            "key": key,
        }
    from exo_control.policy import confirm_ok

    kind = "hklm" if hive_name == "HKEY_LOCAL_MACHINE" else "registry_write"
    if not confirm_ok(confirm, kind=kind):
        return {"ok": False, "error": "registry_delete requires confirm=true", "hive": hive_name, "key": key}
    hive = getattr(winreg, hive_name)
    try:
        if name is not None:
            handle = winreg.OpenKey(hive, key or "", 0, winreg.KEY_SET_VALUE)
            try:
                winreg.DeleteValue(handle, str(name))
            finally:
                winreg.CloseKey(handle)
            return {"ok": True, "hive": hive_name, "key": key, "deleted": "value", "name": str(name)}
        if not key:
            return {"ok": False, "error": "refusing to delete a hive root", "hive": hive_name}
        if recursive:
            _delete_key_tree(winreg, hive, key)
        else:
            parent, _, leaf = key.rpartition("\\")
            handle = winreg.OpenKey(hive, parent, 0, winreg.KEY_WRITE)
            try:
                winreg.DeleteKey(handle, leaf)
            finally:
                winreg.CloseKey(handle)
        return {"ok": True, "hive": hive_name, "key": key, "deleted": "key", "recursive": bool(recursive)}
    except FileNotFoundError:
        return {"ok": True, "hive": hive_name, "key": key, "deleted": "missing", "name": name}
    except OSError as exc:
        failed = {"ok": False, "error": f"delete failed: {exc}", "hive": hive_name, "key": key}
        from exo_control.elevate import retry_if_needed

        return retry_if_needed(
            "registry_delete",
            failed,
            {"path": path, "name": name, "recursive": recursive},
        )


def _delete_key_tree(winreg, hive, key: str) -> None:
    try:
        handle = winreg.OpenKey(hive, key, 0, winreg.KEY_READ | winreg.KEY_WRITE)
    except FileNotFoundError:
        return
    try:
        while True:
            try:
                sub = winreg.EnumKey(handle, 0)
            except OSError:
                break
            _delete_key_tree(winreg, hive, key + "\\" + sub)
        winreg.CloseKey(handle)
    except Exception:
        try:
            winreg.CloseKey(handle)
        except Exception:
            pass
    parent, _, leaf = key.rpartition("\\")
    ph = winreg.OpenKey(hive, parent, 0, winreg.KEY_WRITE)
    try:
        winreg.DeleteKey(ph, leaf)
    finally:
        winreg.CloseKey(ph)
