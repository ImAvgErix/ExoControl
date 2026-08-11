"""Simple macro record / play for repeated desktop flows."""
from __future__ import annotations
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

MACRO_DIR = Path.home() / ".aether" / "macros"


class MacroStore:
    def __init__(self, root: Optional[Path] = None):
        self.root = root or MACRO_DIR
        self.root.mkdir(parents=True, exist_ok=True)
        self._recording: List[Dict[str, Any]] = []
        self._active = False

    def start(self) -> None:
        self._recording = []
        self._active = True

    def stop(self) -> List[Dict[str, Any]]:
        self._active = False
        return list(self._recording)

    def is_recording(self) -> bool:
        return self._active

    def add(self, op: str, **kwargs) -> None:
        if not self._active:
            return
        self._recording.append({"op": op, **kwargs, "ts": time.time()})

    def save(self, name: str, actions: Optional[List[Dict]] = None) -> Path:
        actions = actions if actions is not None else self._recording
        path = self.root / f"{name}.json"
        path.write_text(json.dumps({"name": name, "actions": actions}, indent=2))
        return path

    def load(self, name: str) -> List[Dict[str, Any]]:
        path = self.root / f"{name}.json"
        data = json.loads(path.read_text())
        return data.get("actions") or []

    def list(self) -> List[str]:
        return sorted(p.stem for p in self.root.glob("*.json"))
