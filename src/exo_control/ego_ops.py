"""ego lite status — honesty only.

Exo Control is Windows-only. ego lite (citrolabs/ego-lite) ships a macOS app
today; there is no Windows binary to drive. Agents should use ``browser_*``
Playwright spaces (the local stand-in) or Browser Use Cloud.
"""
from __future__ import annotations

import sys
from typing import Any, Dict


def detect() -> Dict[str, Any]:
    platform = sys.platform
    return {
        "ok": True,
        "provider": "ego-lite",
        "available": False,
        "binary": None,
        "platform": platform,
        "exo_windows_only": True,
        "ego_windows_ready": False,
        "macos": platform == "darwin",
        "hint": (
            "ego lite has no Windows app; Exo Control is Windows-only. "
            "Use browser_* spaces or browser_use (BROWSER_USE_API_KEY)."
        ),
        "docs": "https://github.com/citrolabs/ego-lite",
        "local_standin": "browser_* Playwright spaces",
    }


def exec_js(step: Dict[str, Any]) -> Dict[str, Any]:
    info = detect()
    return {
        "ok": False,
        "error": info["hint"],
        "code": "WINDOWS_ONLY",
        "provider": "ego-lite",
        "platform": info["platform"],
        "docs": info["docs"],
    }
