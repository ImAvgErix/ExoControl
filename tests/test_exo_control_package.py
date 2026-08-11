"""Dual package rename window: exo_control re-exports aether."""
from __future__ import annotations


def test_exo_control_version_matches_aether():
    import aether
    import exo_control
    assert exo_control.__version__ == aether.__version__


def test_exo_control_exec_engine_submodule():
    import exo_control.exec_engine as ee
    import aether.exec_engine as ae
    assert ee.AetherExecEngine is ae.AetherExecEngine


def test_exo_control_compact_surface():
    import exo_control
    assert exo_control.MAX_COMPACT_CHARS <= 4000
    assert callable(exo_control.compact_payload)
