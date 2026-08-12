"""
Action backends for Aether.

Priority (default): Synthetic (UIA/SendInput) → pywinauto → local.
CuaBackend remains optional only if prefer_cua=True and cua-driver is installed.
Agents should not depend on Cua — Synthetic hands cover native + background paths.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class DeliveryResult:
    ok: bool
    backend: str
    message: str = ""
    raw: Any = None
    element_index: Optional[int] = None


class ActionBackend(ABC):
    name: str = "base"

    @abstractmethod
    def available(self) -> bool:
        ...

    @abstractmethod
    def click(self, x: Optional[int] = None, y: Optional[int] = None,
              button: str = "left", **kwargs) -> DeliveryResult:
        ...

    @abstractmethod
    def type_text(self, text: str, **kwargs) -> DeliveryResult:
        ...

    def hotkey(self, keys: List[str]) -> DeliveryResult:
        return DeliveryResult(False, self.name, "hotkey not implemented")

    def list_windows(self) -> List[Dict[str, Any]]:
        return []

    def get_window_state(self, pid: int, window_id: Optional[int] = None) -> Dict[str, Any]:
        return {}


class LocalBackend(ActionBackend):
    name = "local"

    def __init__(self):
        from .action import ActionEngine
        try:
            self.engine = ActionEngine()
            self._ok = True
        except Exception:
            self.engine = None
            self._ok = False

    def available(self) -> bool:
        return bool(self._ok)

    @staticmethod
    def _unpack(r) -> tuple:
        """ActionEngine returns log dicts; getattr on a dict always defaulted to
        True, so failed input was reported as success."""
        if isinstance(r, dict):
            ok = bool(r.get("success", False))
            details = r.get("details") or {}
            msg = details.get("error") or r.get("action") or str(r)
            return ok, str(msg)
        return bool(getattr(r, "success", True)), str(getattr(r, "message", r))

    def click(self, x: Optional[int] = None, y: Optional[int] = None,
              button: str = "left", **kwargs) -> DeliveryResult:
        ok, msg = self._unpack(self.engine.click(x=x, y=y, button=button))
        return DeliveryResult(ok, "local", msg)

    def type_text(self, text: str, **kwargs) -> DeliveryResult:
        clear = kwargs.get("clear", False)
        ok, msg = self._unpack(self.engine.type_text(text, clear_first=clear))
        return DeliveryResult(ok, "local", msg)

    def hotkey(self, keys: List[str]) -> DeliveryResult:
        ok, msg = self._unpack(self.engine.hotkey(*keys))
        return DeliveryResult(ok, "local", msg)


class CuaBackend(ActionBackend):
    """
    Real Cua Driver integration via CLI.
    Gives background, window-scoped, accessibility-element clicks.
    """
    name = "cua"

    def __init__(self, binary: str = "cua-driver"):
        self.binary = binary
        self._version: Optional[str] = None

    def available(self) -> bool:
        if not shutil.which(self.binary):
            return False
        try:
            r = subprocess.run(
                [self.binary, "--version"],
                capture_output=True, text=True, timeout=4
            )
            if r.returncode == 0:
                self._version = (r.stdout or r.stderr or "").strip()
                return True
        except Exception:
            pass
        return False

    def _call(self, tool: str, payload: Optional[Dict] = None, timeout: int = 45) -> Dict[str, Any]:
        args = [self.binary, "call", tool]
        if payload is not None:
            args.append(json.dumps(payload))
        try:
            r = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
            out = (r.stdout or "").strip()
            err = (r.stderr or "").strip()
            if r.returncode != 0:
                return {"ok": False, "error": err or out or f"exit {r.returncode}"}
            if not out:
                return {"ok": True, "raw": ""}
            try:
                return json.loads(out)
            except json.JSONDecodeError:
                # Cua often prints human text + optional JSON
                return {"ok": True, "raw": out}
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": "timeout"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def list_windows(self) -> List[Dict[str, Any]]:
        # Try common tool names across Cua versions
        for tool in ("list_apps", "list_windows", "get_apps"):
            res = self._call(tool, {})
            if res.get("ok") is False and "error" in res:
                continue
            # Normalize various shapes
            if isinstance(res, list):
                return res
            for key in ("apps", "windows", "data", "result"):
                if key in res and isinstance(res[key], list):
                    return res[key]
            if res.get("raw"):
                return [{"raw": res["raw"]}]
        return []

    def get_window_state(self, pid: int, window_id: Optional[int] = None) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"pid": pid}
        if window_id is not None:
            payload["window_id"] = window_id
        return self._call("get_window_state", payload)

    def click(
        self,
        x: Optional[int] = None,
        y: Optional[int] = None,
        button: str = "left",
        pid: Optional[int] = None,
        window_id: Optional[int] = None,
        element_index: Optional[int] = None,
        **kwargs,
    ) -> DeliveryResult:
        # Prefer accessibility element click (true Cua strength)
        if pid is not None and element_index is not None:
            payload: Dict[str, Any] = {
                "pid": pid,
                "element_index": element_index,
            }
            if window_id is not None:
                payload["window_id"] = window_id
            if button and button != "left":
                payload["button"] = button
            res = self._call("click", payload)
            ok = res.get("ok", True) is not False and "error" not in res
            return DeliveryResult(
                ok=ok,
                backend="cua",
                message=res.get("raw") or res.get("error") or f"element_index={element_index}",
                raw=res,
                element_index=element_index,
            )

        # Coordinate click fallback (still through Cua when possible)
        if x is not None and y is not None:
            payload = {"x": int(x), "y": int(y), "button": button}
            if pid is not None:
                payload["pid"] = pid
            if window_id is not None:
                payload["window_id"] = window_id
            res = self._call("click", payload)
            ok = res.get("ok", True) is not False and "error" not in res
            return DeliveryResult(
                ok=ok,
                backend="cua",
                message=res.get("raw") or res.get("error") or f"coords=({x},{y})",
                raw=res,
            )

        return DeliveryResult(False, "cua", "need element_index or x/y")

    def type_text(self, text: str, **kwargs) -> DeliveryResult:
        payload: Dict[str, Any] = {"text": text}
        for k in ("pid", "window_id", "element_index"):
            if kwargs.get(k) is not None:
                payload[k] = kwargs[k]
        res = self._call("type", payload)
        # Some Cua versions use "type_text" or "keydown"
        if res.get("ok") is False or "error" in res:
            res = self._call("type_text", payload)
        ok = res.get("ok", True) is not False and "error" not in res
        return DeliveryResult(ok, "cua", res.get("raw") or res.get("error") or "typed", raw=res)

    def launch_app(self, name_or_bundle: str) -> DeliveryResult:
        # Try common shapes
        for payload in (
            {"name": name_or_bundle},
            {"bundle_id": name_or_bundle},
            {"app": name_or_bundle},
        ):
            res = self._call("launch_app", payload)
            if res.get("ok") is not False and "error" not in res:
                return DeliveryResult(True, "cua", str(res), raw=res)
        return DeliveryResult(False, "cua", f"could not launch {name_or_bundle}")


def get_best_backend(prefer_cua: bool = False, prefer_synthetic: bool = True) -> ActionBackend:
    """Priority: Synthetic (custom) → pywinauto → local. Optional Cua only if prefer_cua."""
    if prefer_cua:
        cua = CuaBackend()
        if cua.available():
            return cua
    if prefer_synthetic:
        try:
            from .synthetic import SyntheticBackend
            syn = SyntheticBackend()
            if syn.available():
                return syn
        except Exception:
            pass
    try:
        from .backends_win import PywinautoBackend
        win = PywinautoBackend()
        if win.available():
            return win
    except Exception:
        pass
    return LocalBackend()

