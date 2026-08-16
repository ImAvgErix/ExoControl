"""2.4 owner surface: pc snapshot, files extras, find, confirm gates."""
from __future__ import annotations

import time
from pathlib import Path

import pytest

from aether.exec_engine import ExoExecEngine, MAX_STEPS
from aether.ops_catalog import CORE_OPS, known_ops, lease_required_ops, list_ops
from aether import pc


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("EXO_HOME", str(tmp_path / "exo"))
    monkeypatch.setenv("EXO_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("EXO_LOCK_DIR", str(tmp_path / "locks"))
    monkeypatch.setenv("EXO_FILE_ROOTS", str(tmp_path / "workspace"))
    monkeypatch.setenv("EXO_DISABLE_ELEVATE", "1")
    monkeypatch.delenv("EXO_TRUST", raising=False)
    monkeypatch.delenv("EXO_FULL_TRUST", raising=False)
    (tmp_path / "workspace").mkdir()
    (tmp_path / "state").mkdir()
    yield tmp_path


def test_catalog_includes_owner_ops():
    names = known_ops()
    for op in (
        "find", "pc", "audio", "power", "idle", "lock", "sleep",
        "wifi", "wifi_connect", "recycle", "recycle_empty",
        "package", "files_hash", "files_zip", "watch_file",
        "right_click", "double_click", "menu", "copy", "paste",
    ):
        assert op in names
    req = lease_required_ops()
    assert "lock" in req
    assert "sleep" in req
    assert "right_click" in req
    assert "find" not in req
    assert "audio" not in req
    compact = list_ops()
    ops = {row["op"] for row in compact["ops"]}
    assert "find" in ops
    assert "pc" in ops
    assert compact["count"] == len(CORE_OPS)


def test_max_steps_is_128():
    assert MAX_STEPS >= 128


def test_sleep_wifi_recycle_need_confirm(home):
    assert pc.sleep(confirm=False)["ok"] is False
    assert pc.wifi_connect("x", confirm=False)["ok"] is False
    assert pc.recycle_empty(confirm=False)["ok"] is False
    assert pc.package(action="install", id="Nope.Id", confirm=False)["ok"] is False


def test_clock_idle_power_status(home):
    clk = pc.clock()
    assert clk["ok"] is True
    assert clk["epoch"] > 0
    idle = pc.idle()
    assert idle["ok"] is True
    assert idle["idle_ms"] >= 0
    snap = pc.status()
    assert snap["ok"] is True
    assert snap["clock"]["ok"] is True
    assert "power" in snap
    assert "audio" in snap


def test_files_hash_zip_touch_watch(home):
    ws = home / "workspace"
    src = ws / "note.txt"
    src.write_text("hello-exo", encoding="utf-8")
    hashed = pc.files_hash(str(src), roots=[ws])
    assert hashed["ok"] is True
    assert len(hashed["sha256"]) == 64
    zipped = pc.files_zip(str(src), str(ws / "note.zip"), roots=[ws])
    assert zipped["ok"] is True
    dest = ws / "out"
    unzipped = pc.files_unzip(str(ws / "note.zip"), str(dest), roots=[ws])
    assert unzipped["ok"] is True
    assert (dest / "note.txt").read_text(encoding="utf-8") == "hello-exo"
    touched = pc.files_touch(str(ws / "new.txt"), roots=[ws])
    assert touched["ok"] is True
    late = ws / "late.txt"
    started = time.perf_counter()

    def _write_later():
        time.sleep(0.15)
        late.write_text("x", encoding="utf-8")

    import threading
    threading.Thread(target=_write_later, daemon=True).start()
    watched = pc.watch_file(str(late), state="exists", timeout=2.0, poll=0.05, roots=[ws])
    assert watched["ok"] is True
    assert time.perf_counter() - started < 2.0


def test_zip_slip_rejected(home):
    ws = home / "workspace"
    evil = ws / "evil.zip"
    import zipfile
    with zipfile.ZipFile(evil, "w") as zf:
        zf.writestr("../outside.txt", "nope")
    out = pc.files_unzip(str(evil), str(ws / "safe"), roots=[ws])
    assert out["ok"] is False


def test_engine_find_and_pc(home):
    class Stub:
        _focus_pid = 7
        _focus_window_id = 9

        def status(self):
            return {"ok": True}

        def read_ui(self, **kwargs):
            return {
                "ok": True,
                "pid": 7,
                "elements": [
                    {"name": "Save", "role": "button", "element_index": 3},
                    {"name": "Cancel", "role": "button", "element_index": 4},
                ],
            }

        def compact_observe(self, **kwargs):
            return self.read_ui()

    eng = ExoExecEngine(controller=Stub())
    out = eng.execute(
        [
            {"op": "find", "query": "save"},
            {"op": "pc", "action": "clock"},
            {"op": "idle"},
            {"op": "help", "query": "wifi_connect", "detail": True},
        ]
    )
    assert out["ok"] is True, out
    found = out["steps"][0]["result"]
    assert found["count"] == 1
    assert found["matches"][0]["name"] == "Save"
    assert found["matches"][0]["ref"] == "e0"
    assert out["steps"][1]["result"]["ok"] is True
    assert out["steps"][2]["result"]["ok"] is True
    body = out["steps"][3]["result"]
    assert any(o["op"] == "wifi_connect" for o in body["ops"])


def test_engine_files_and_confirm_gates(home):
    ws = home / "workspace"
    eng = ExoExecEngine()
    out = eng.execute(
        [
            {"op": "lease_acquire", "agent_id": "pc", "task": "files", "ttl_sec": 30},
            {"op": "files_touch", "path": str(ws / "a.txt")},
            {"op": "files_write", "path": str(ws / "a.txt"), "text": "abc"},
            {"op": "files_hash", "path": str(ws / "a.txt")},
            {"op": "files_zip", "path": str(ws / "a.txt"), "dest": str(ws / "a.zip")},
            {"op": "sleep", "stop_on_failure": False},
            {"op": "recycle_empty", "stop_on_failure": False},
            {"op": "lease_release"},
        ]
    )
    assert out["steps"][1]["ok"] is True
    assert out["steps"][3]["result"]["ok"] is True
    assert out["steps"][4]["result"]["ok"] is True
    assert out["steps"][5]["ok"] is False
    assert "confirm" in (out["steps"][5]["result"].get("error") or "")
    assert out["steps"][6]["ok"] is False


def test_cli_pc_status(home, capsys):
    from exo_control.cli import main

    rc = main(["pc", "clock"])
    captured = capsys.readouterr()
    assert rc == 0
    assert "epoch" in captured.out or "local" in captured.out
