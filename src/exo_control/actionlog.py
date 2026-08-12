"""Append-only action log for debugging / replay hints."""
from __future__ import annotations
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

def _default_log() -> Path:
    from exo_control.paths import state_dir
    return state_dir() / "action_log.jsonl"


class ActionLog:
    def __init__(self, path: Optional[Path] = None, enabled: bool = True):
        self._path_override = path
        self.enabled = enabled

    @property
    def path(self) -> Path:
        return self._path_override or _default_log()

    def record(self, event: str, **payload) -> None:
        if not self.enabled:
            return
        row = {"ts": time.time(), "event": event, **payload}
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(row, default=str) + "\n")
        except Exception:
            pass

    def tail(self, n: int = 20) -> List[Dict[str, Any]]:
        if not self.path.exists():
            return []
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()
            out = []
            for line in lines[-n:]:
                try:
                    out.append(json.loads(line))
                except Exception:
                    continue
            return out
        except Exception:
            return []
