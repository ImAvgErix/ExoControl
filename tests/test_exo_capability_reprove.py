"""Regressions from Exo Control capability re-prove gaps."""
from __future__ import annotations

from pathlib import Path

from aether.files_ops import files_copy, files_write, default_roots
from aether import infra_ops


def test_files_copy_accepts_path_dest_aliases(tmp_path, monkeypatch):
    monkeypatch.setenv("AETHER_FILE_ROOTS", str(tmp_path))
    # also default workspace unused when roots passed... files_copy uses default_roots unless roots=
    src = tmp_path / "a.txt"
    dst = tmp_path / "sub" / "b.txt"
    src.write_text("hello", encoding="utf-8")
    out = files_copy(path=str(src), dest=str(dst), roots=[tmp_path])
    assert out["ok"] is True, out
    assert dst.read_text(encoding="utf-8") == "hello"


def test_files_copy_empty_dst_does_not_resolve_cwd(tmp_path):
    src = tmp_path / "a.txt"
    src.write_text("x", encoding="utf-8")
    out = files_copy(src=str(src), dst="", roots=[tmp_path])
    assert out["ok"] is False
    assert "requires" in out["error"]


def test_service_list_parses_padded_state_lines(monkeypatch):
    sample = """
SERVICE_NAME: FooSvc
DISPLAY_NAME: Foo
        TYPE               : 10  WIN32_OWN_PROCESS
        STATE              : 4  RUNNING
        WIN32_EXIT_CODE    : 0  (0x0)

SERVICE_NAME: BarSvc
DISPLAY_NAME: Bar
        STATE              : 1  STOPPED
"""

    class R:
        returncode = 0
        stdout = sample
        stderr = ""

    monkeypatch.setattr(infra_ops, "_run", lambda *a, **k: R())
    out = infra_ops.service_list(max_items=10)
    assert out["ok"] is True
    assert out["count"] == 2
    assert out["services"][0] == {"name": "FooSvc", "state": "RUNNING"}
    assert out["services"][1]["name"] == "BarSvc"
