"""Live Windows acceptance: launch Notepad, type, read, close.

Skipped automatically when there is no interactive desktop or launch fails.
Set EXO_LIVE=0 to force-skip. Set EXO_LIVE=1 to fail instead of skip.
"""
from __future__ import annotations

import os
import sys

import pytest

from aether.exec_engine import ExoExecEngine


def _want_live() -> str:
    return (os.environ.get("EXO_LIVE") or "").strip()


@pytest.mark.live
@pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
def test_notepad_type_read_close():
    if _want_live() == "0":
        pytest.skip("EXO_LIVE=0")
    eng = ExoExecEngine()
    marker = "exo-control-live-1.3"
    out = eng.execute(
        {
            "steps": [
                {"op": "lease_acquire", "agent_id": "live-notepad", "task": "accept", "ttl_sec": 90},
                {"op": "launch", "app": "notepad", "timeout": 12},
                {"op": "focus", "title": "Notepad"},
                {"op": "type", "text": marker},
                {"op": "read"},
                {"op": "verify", "expect": [marker], "timeout": 6},
            ],
            "finally": [
                {"op": "window_close", "title": "Notepad", "discard_unsaved": True},
                {"op": "lease_release"},
            ],
        }
    )
    if not out.get("ok"):
        err = (out.get("last_error") or {}).get("error") or ""
        launch = next((s for s in out.get("steps") or [] if s.get("op") == "launch"), None)
        if _want_live() != "1" and launch and not launch.get("ok"):
            pytest.skip(f"notepad launch failed: {launch.get('result')}")
        if _want_live() != "1" and "desktop" in str(err).lower():
            pytest.skip(f"no interactive desktop: {err}")
    assert out["ok"] is True, out.get("last_error") or out
    read = next(s for s in out["steps"] if s["op"] == "read")
    blob = str(read["result"])
    assert marker in blob or any(
        marker in str(s["result"]) for s in out["steps"] if s["op"] in {"verify", "type"}
    )
