"""Simple runtime config for Exo Control."""
from __future__ import annotations
import json
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Any, Dict, Optional


def _default_config_path() -> Path:
    from exo_control.paths import config_path, legacy_aether_root
    preferred = config_path()
    if preferred.exists():
        return preferred
    legacy = legacy_aether_root() / "config.json"
    if legacy.exists():
        return legacy
    return preferred


DEFAULT_PATH = _default_config_path()  # resolved at import; load() re-resolves


@dataclass
class ExoConfig:
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
        path = path or _default_config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2))

    @classmethod
    def load(cls, path: Optional[Path] = None) -> "ExoConfig":
        path = path or _default_config_path()
        if not path.exists():
            return cls()
        try:
            data = json.loads(path.read_text())
            known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore
            filtered = {k: v for k, v in data.items() if k in known}
            return cls(**filtered)
        except Exception:
            return cls()


# Compat alias
AetherConfig = ExoConfig
