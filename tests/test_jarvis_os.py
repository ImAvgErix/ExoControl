"""Jarvis OS P0 CODE: compact eyes, files allowroot, registry, infra gates."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from aether.compact import MAX_COMPACT_CHARS, MAX_COMPACT_REFS, compact_payload
from aether.exec_engine import AetherExecEngine
from aether import files_ops
from aether import registry_ops
from aether import infra_ops
from aether import desktop_lease


@pytest.fixture
def lease_home(tmp_path, monkeypatch):
    monkeypatch.setenv("AETHER_LOCK_DIR", str(tmp_path / "locks"))
    monkeypatch.setenv("AETHER_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("AETHER_FILE_ROOTS", str(tmp_path / "workspace"))
    (tmp_path / "workspace").mkdir(parents=True, exist_ok=True)
    yield tmp_path


class EyesStub:
    def __init__(self):
        self._focus_pid = 1
        self._focus_window_id = 10

    def status(self):
        return {"ok": True}

    def compact_observe(self, include_ocr=False, max_ocr=40, max_elements=30):
        return {
            "ok": True,
            "a11y_labels": [f"L{i}" for i in range(80)],
            "elements": [{"ref": i, "name": f"E{i}"} for i in range(80)],
            "screenshot_base64": "iVBORxxxxxxxx" + ("A" * 9000),
            "raw_html": "<html>" + ("x" * 5000) + "</html>",
            "text_sample": "hello " * 2000,
            "include_ocr": include_ocr,
        }

    def read_ui(self, force=True, interactive_only=False, max_elements=120):
        return self.compact_observe()


class FakeBrowser:
    def __init__(self):
        self.clicks = 0
        self.snapshots = 0

    def snapshot(self, space_id=None, include_screenshot=False):
        self.snapshots += 1
        return {
            "ok": True,
            "elements": [{"ref": 1, "name": "Go"}, {"ref": 2, "name": "Back"}],
            "screenshot_base64": "iVBORyy" + ("B" * 9000),
        }

    def click(self, ref=None, selector=None, x=None, y=None, space_id=None,
              text=None, name=None, query=None):
        self.clicks += 1
        if self.clicks == 1 and ref == 99:
            return {"ok": False, "error": "No element for ref=99"}
        return {"ok": True, "ref": ref, "clicked": True}


def test_compact_payload_strips_screenshot_and_caps():
    fat = {
        "ok": True,
        "screenshot_base64": "iVBORxx" + ("Z" * 10000),
        "annotated_screenshot_base64": "abc",
        "raw_html": "<html>huge</html>",
        "html": "<div/>",
        "elements": [{"ref": i} for i in range(100)],
        "text_sample": "word " * 5000,
    }
    out = compact_payload(fat, verbose=False)
    assert out["_compact"] is True
    assert "screenshot_base64" not in out
    assert "raw_html" not in out
    assert "html" not in out
    assert len(out.get("elements") or []) <= MAX_COMPACT_REFS
    assert out["_chars"] <= MAX_COMPACT_CHARS + 200  # rough; meta overhead
    # verbose keeps structure but still drops absurd blobs/strip keys
    verbose = compact_payload(fat, verbose=True)
    assert "screenshot_base64" not in verbose
    assert len(verbose.get("elements") or []) == 100


def test_observe_and_snapshot_get_compact_flag(lease_home, monkeypatch):
    eng = AetherExecEngine(controller=EyesStub())
    fake = FakeBrowser()
    eng._get_browser = lambda: fake  # type: ignore
    # lease for browser_snapshot
    out = eng.execute(
        [
            {"op": "observe"},
            {"op": "lease_acquire", "agent": "os", "task": "snap", "ttl_sec": 60},
            {"op": "browser_snapshot"},
            {"op": "lease_release"},
        ]
    )
    assert out["steps"][0]["result"].get("_compact") is True
    assert "screenshot_base64" not in out["steps"][0]["result"]
    assert out["steps"][2]["result"].get("_compact") is True
    assert eng._last_browser_refs and len(eng._last_browser_refs) == 2

    verbose = eng.execute([{"op": "observe", "verbose": True}])
    assert verbose["steps"][0]["result"].get("_compact") is not True


def test_files_outside_root_gates(lease_home, monkeypatch):
    root = lease_home / "workspace"
    outside = lease_home / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("nope", encoding="utf-8")
    (root / "ok.txt").write_text("yes", encoding="utf-8")

    denied = files_ops.files_list(str(outside), confirm=False)
    assert denied["ok"] is False
    assert "confirm" in denied["error"]

    allowed = files_ops.files_list(str(outside), confirm=True)
    assert allowed["ok"] is True

    # recursive delete denied without confirm
    nest = root / "nest"
    nest.mkdir()
    (nest / "a.txt").write_text("x", encoding="utf-8")
    deny_del = files_ops.files_delete(str(nest), confirm=False, recursive=True)
    assert deny_del["ok"] is False
    assert "confirm" in deny_del["error"]

    # audit file exists after deny
    audit = Path(lease_home / "state" / "files_audit.jsonl")
    assert audit.exists()
    lines = audit.read_text(encoding="utf-8").strip().splitlines()
    assert any("denied" in ln for ln in lines)

    eng = AetherExecEngine(controller=EyesStub())
    # mutating write needs lease
    wrote = eng.execute(
        [
            {"op": "lease_acquire", "agent": "f", "task": "w", "ttl_sec": 30},
            {"op": "files_write", "path": str(root / "w.txt"), "text": "hi"},
            {"op": "files_read", "path": str(root / "w.txt")},
            {"op": "lease_release"},
        ]
    )
    assert wrote["ok"] is True
    assert wrote["steps"][2]["result"]["text"] == "hi"


def test_registry_gates(lease_home, monkeypatch):
    missing = registry_ops.registry_read(r"HKCU\Software\AetherJarvisOSDoesNotExist\Missing")
    assert missing["ok"] is False

    no_confirm = registry_ops.registry_write(
        r"HKCU\Software\AetherJarvisOSTest",
        name="Flag",
        value="1",
        confirm=False,
    )
    assert no_confirm["ok"] is False
    assert "confirm" in no_confirm["error"]

    hklm = registry_ops.registry_write(
        r"HKLM\Software\AetherJarvisOSTest",
        name="Flag",
        value="1",
        confirm=True,
    )
    assert hklm["ok"] is False
    assert "HKLM" in hklm["error"]

    eng = AetherExecEngine(controller=EyesStub())
    out = eng.execute(
        [
            {"op": "registry_read", "path": r"HKCU\Software\Microsoft\Windows\CurrentVersion"},
            {"op": "lease_acquire", "agent": "r", "task": "reg", "ttl_sec": 30},
            {
                "op": "registry_write",
                "path": r"HKCU\Software\AetherJarvisOSTest",
                "name": "P0",
                "value": "1",
                "type": "string",
                "confirm": True,
            },
            {"op": "lease_release"},
        ]
    )
    assert out["steps"][0]["result"]["ok"] is True
    assert out["steps"][2]["result"]["ok"] is True


def test_protected_process_kill_denied(lease_home, monkeypatch):
    monkeypatch.setattr(infra_ops, "_proc_name_for_pid", lambda pid: "EasyAntiCheat.exe")
    out = infra_ops.kill_proc(12345, confirm=True)
    assert out["ok"] is False
    assert out.get("reason") == "protected_process" or out.get("error") == "protected_process"


def test_protected_via_exec(lease_home, monkeypatch):
    monkeypatch.setattr("aether.infra_ops._proc_name_for_pid", lambda pid: "FACEITClient.exe")
    eng = AetherExecEngine(controller=EyesStub())
    out = eng.execute(
        [
            {"op": "lease_acquire", "agent": "k2", "task": "kill", "ttl_sec": 30},
            {"op": "proc", "action": "kill", "pid": 777, "confirm": True},
            {"op": "lease_release", "stop_on_failure": False},
        ]
    )
    res = out["steps"][1]["result"]
    assert res["ok"] is False
    assert res.get("error") == "protected_process" or res.get("reason") == "protected_process"


def test_service_control_requires_confirm(lease_home):
    out = infra_ops.service_control("Spooler", "stop", confirm=False)
    assert out["ok"] is False
    assert "confirm" in out["error"]

    eng = AetherExecEngine(controller=EyesStub())
    denied = eng.execute(
        [
            {"op": "lease_acquire", "agent": "svc", "task": "svc", "ttl_sec": 30},
            {"op": "service_control", "name": "Spooler", "action": "stop"},
        ]
    )
    assert denied["steps"][1]["result"]["ok"] is False
    st = desktop_lease.status()
    if st.get("token"):
        desktop_lease.release(st["token"])


def test_observe_budget_stats(lease_home):
    eng = AetherExecEngine(controller=EyesStub())
    out = eng.execute([{"op": "observe_budget", "n": 5, "include_ocr": False}])
    res = out["steps"][0]["result"]
    assert res["ok"] is True
    for key in ("p50_ms", "p95_ms", "p95_chars", "n"):
        assert key in res
    assert res["n"] == 5


def test_structure_miss_retries_once(lease_home):
    eng = AetherExecEngine(controller=EyesStub())
    fake = FakeBrowser()
    eng._get_browser = lambda: fake  # type: ignore
    out = eng.execute(
        [
            {"op": "lease_acquire", "agent": "b", "task": "click", "ttl_sec": 30},
            {"op": "browser_click", "ref": 99},
            {"op": "lease_release"},
        ]
    )
    # first miss + retry => 2 clicks, 1 snapshot
    assert fake.clicks == 2
    assert fake.snapshots == 1
    assert out["steps"][1]["result"].get("structure_miss_retry") is True