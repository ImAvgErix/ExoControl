"""Simple runtime config for Exo Control."""
from __future__ import annotations
import json
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Any, Dict, Optional

DEFAULT_PATH = Path.home() / ".aether" / "config.json"


@dataclass
class AetherConfig:
    prefer_cua: bool = False  # Synthetic hands are first-class; Cua not required
    max_retries: int = 3
    verify: bool = True
    similarity_threshold: float = 0.97
    cache_ttl: float = 0.35
    headless_browser: bool = False
    max_actions_per_minute: int = 90
    max_clicks_per_minute: int = 45
    browser_profile_dir: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)

    def save(self, path: Optional[Path] = None) -> None:
        path = path or DEFAULT_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2))

    @classmethod
    def load(cls, path: Optional[Path] = None) -> "AetherConfig":
        path = path or DEFAULT_PATH
        if not path.exists():
            return cls()
        try:
            data = json.loads(path.read_text())
            known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore
            filtered = {k: v for k, v in data.items() if k in known}
            return cls(**filtered)
        except Exception:
            return cls()
