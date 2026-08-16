"""Unit tests stay off the live eyes loop unless a test opts in."""
from __future__ import annotations

import os


def pytest_configure():
    if os.environ.get("EXO_LIVE") == "1":
        os.environ.setdefault("EXO_LIVE_EYES", "1")
    else:
        os.environ.setdefault("EXO_LIVE_EYES", "0")
        # Isolated unit tests must not inherit operator Full-Trust / kill env.
        os.environ["EXO_TRUST"] = "default"
        os.environ.pop("EXO_FULL_TRUST", None)
        os.environ.pop("AETHER_FULL_TRUST", None)
        os.environ.pop("EXO_KILL_SWITCH", None)
