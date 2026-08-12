"""Unit tests stay off the live eyes loop unless a test opts in."""
from __future__ import annotations

import os


def pytest_configure():
    if os.environ.get("EXO_LIVE") == "1":
        os.environ.setdefault("EXO_LIVE_EYES", "1")
    else:
        os.environ.setdefault("EXO_LIVE_EYES", "0")
