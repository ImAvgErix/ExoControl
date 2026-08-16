"""Announce-GA DoR hard stops — confirm gates, anti-cheat deny, compact caps.

This module is the charter proof artifact for:
docs/CHARTER.md → Packaging outcomes → Hard stops tested.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from aether.compact import MAX_COMPACT_CHARS, MAX_COMPACT_REFS, compact_payload
from aether import files_ops, infra_ops, registry_ops
from aether.exec_engine import AetherExecEngine


@pytest.fixture
def lease_home(tmp_path, monkeypatch):
    monkeypatch.setenv("AETHER_LOCK_DIR", str(tmp_path / "locks"))
    monkeypatch.setenv("AETHER_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("AETHER_FILE_ROOTS", str(tmp_path / "workspace"))
    (tmp_path / "workspace").mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("EXO_DISABLE_ELEVATE", "1")
    monkeypatch.delenv("EXO_TRUST", raising=False)
    monkeypatch.delenv("EXO_FULL_TRUST", raising=False)
    yield tmp_path


# --- compact caps ---

def test_dor_compact_caps_constants():
    assert MAX_COMPACT_CHARS <= 4000
    assert MAX_COMPACT_REFS <= 40


def test_dor_compact_payload_under_cap():
    fat = {
        "screenshot_base64": "i" * 50000,
        "raw_html": "<html>" + ("x" * 20000) + "</html>",
        "elements": [{"ref": f"e{i}", "text": "n" * 200} for i in range(200)],
        "text_sample": "y" * 20000,
    }
    out = compact_payload(fat, verbose=False)
    assert "screenshot_base64" not in out
    assert "raw_html" not in out
    assert len(out.get("elements") or []) <= MAX_COMPACT_REFS
    # serialized size under hard char cap (+ small meta slack)
    import json
    blob = json.dumps(out, ensure_ascii=False, default=str)
    assert len(blob) <= MAX_COMPACT_CHARS + 512


# --- confirm gates ---

def test_dor_files_mutating_require_confirm_outside_root(lease_home, monkeypatch):
    outside = lease_home / "outside.txt"
    outside.write_text("nope", encoding="utf-8")
    denied = files_ops.files_write(str(outside), "x", confirm=False, roots=[lease_home / "workspace"])
    assert denied["ok"] is False
    assert "allowroot" in denied["error"] or "EXO_" in denied["error"] or "confirm" in denied["error"]


def test_dor_files_recursive_delete_requires_confirm(lease_home):
    root = lease_home / "workspace"
    nest = root / "wipe_me"
    nest.mkdir(parents=True, exist_ok=True)
    (nest / "f.txt").write_text("z", encoding="utf-8")
    denied = files_ops.files_delete(str(nest), confirm=False, recursive=True, roots=[root])
    assert denied["ok"] is False
    assert "confirm" in denied["error"]


def test_dor_registry_write_requires_confirm():
    out = registry_ops.registry_write(
        r"HKCU\Software\ExoControlDoRTest",
        name="flag",
        value="1",
        confirm=False,
    )
    assert out["ok"] is False
    assert "confirm" in out["error"]


def test_dor_service_control_requires_confirm():
    out = infra_ops.service_control("Spooler", "stop", confirm=False)
    assert out["ok"] is False
    assert "confirm" in out["error"]


def test_dor_proc_kill_requires_confirm():
    out = infra_ops.kill_proc(1, confirm=False)
    assert out["ok"] is False
    assert "confirm" in out.get("error", "")


# --- anti-cheat / protected deny ---

@pytest.mark.parametrize(
    "name",
    [
        "EasyAntiCheat.exe",
        "BattlEye.exe",
        "vgc.exe",
        "FACEITClient.exe",
        "Ricochet.exe",
    ],
)
def test_dor_protected_process_names_detected(name):
    assert infra_ops.is_protected_process(name) is True


def test_dor_protected_kill_denied_even_with_confirm(monkeypatch):
    monkeypatch.setattr(infra_ops, "_proc_name_for_pid", lambda pid: "EasyAntiCheat.exe")
    out = infra_ops.kill_proc(4242, confirm=True)
    assert out["ok"] is False
    assert out.get("reason") == "protected_process" or out.get("error") == "protected_process"


def test_dor_protected_kill_by_name_no_pid():
    out = infra_ops.kill_proc(name="vgc.exe", confirm=True)
    assert out["ok"] is False
    assert out.get("reason") == "protected_process" or out.get("error") == "protected_process"


def test_dor_protected_kill_via_exec(lease_home, monkeypatch):
    monkeypatch.setattr("aether.infra_ops._proc_name_for_pid", lambda pid: "BattlEye.exe")
    eng = AetherExecEngine()
    out = eng.execute(
        [
            {"op": "lease_acquire", "agent": "dor-hard-stops", "task": "kill", "ttl_sec": 30},
            {"op": "proc", "action": "kill", "pid": 99, "confirm": True},
            {"op": "lease_release", "stop_on_failure": False},
        ]
    )
    step = out["steps"][1]["result"]
    assert step.get("ok") is False
    assert step.get("reason") == "protected_process" or step.get("error") == "protected_process"
