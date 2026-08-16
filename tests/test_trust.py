"""Trust levels, Full-Trust ack, kill file, confirm_ok, protected paths."""
from __future__ import annotations

from pathlib import Path

import pytest

from aether.exec_engine import ExoExecEngine
from aether import files_ops, infra_ops, registry_ops, trust
from aether.policy import confirm_ok, identity
from aether.safety import SafetyConfig, SafetyGate


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("EXO_HOME", str(tmp_path / "exo"))
    monkeypatch.setenv("EXO_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("EXO_LOCK_DIR", str(tmp_path / "locks"))
    monkeypatch.setenv("EXO_FILE_ROOTS", str(tmp_path / "workspace"))
    monkeypatch.delenv("EXO_TRUST", raising=False)
    monkeypatch.delenv("EXO_FULL_TRUST", raising=False)
    monkeypatch.delenv("EXO_ALLOW_OUTSIDE_ROOTS", raising=False)
    monkeypatch.delenv("EXO_ALLOW_FORCE_RELEASE", raising=False)
    monkeypatch.delenv("EXO_KILL_SWITCH", raising=False)
    monkeypatch.setenv("EXO_DISABLE_ELEVATE", "1")
    (tmp_path / "workspace").mkdir()
    (tmp_path / "state").mkdir()
    yield tmp_path


def _ack(source="test"):
    return trust.enable_full_trust(ack="I own this PC", confirm=True, source=source)


def test_default_requires_confirm(home):
    assert trust.active_level() == "default"
    assert confirm_ok(False, kind="proc_kill") is False
    assert confirm_ok(True, kind="proc_kill") is True
    out = infra_ops.kill_proc(1, confirm=False)
    assert out["ok"] is False
    assert "confirm" in out["error"]


def test_env_alone_does_not_activate_full(home, monkeypatch):
    monkeypatch.setenv("EXO_TRUST", "full")
    assert trust.requested_level() == "full"
    assert trust.full_trust_active() is False
    assert trust.active_level() == "default"
    st = trust.status()
    assert st["ack"] is False
    assert "ack" in (st.get("hint") or "").lower()


def test_ack_alone_does_not_activate_full(home):
    _ack()
    assert trust.ack_present() is True
    assert trust.full_trust_active() is False
    assert trust.active_level() == "default"


def test_full_trust_needs_env_and_ack(home, monkeypatch):
    monkeypatch.setenv("EXO_TRUST", "full")
    _ack()
    assert trust.full_trust_active() is True
    assert trust.active_level() == "full"
    assert confirm_ok(False, kind="proc_kill") is True
    assert confirm_ok(False, kind="hklm") is True


def test_full_trust_alias_env(home, monkeypatch):
    monkeypatch.setenv("EXO_FULL_TRUST", "1")
    _ack()
    assert trust.full_trust_active() is True


def test_wrong_ack_phrase_rejected(home):
    out = trust.enable_full_trust(ack="please", confirm=True, source="test")
    assert out["ok"] is False
    assert trust.ack_present() is False


def test_trusted_level(home, monkeypatch):
    monkeypatch.setenv("EXO_TRUST", "trusted")
    assert trust.active_level() == "trusted"
    assert trust.confirms_optional() is False
    assert trust.max_lease_ttl_sec() >= 4 * 3600
    assert trust.rate_limit_multiplier() == 3.0


def test_full_trust_lease_ttl(home, monkeypatch):
    monkeypatch.setenv("EXO_TRUST", "full")
    _ack()
    assert trust.max_lease_ttl_sec() >= 8 * 3600


def test_recursive_delete_optional_in_full_trust(home, monkeypatch):
    root = home / "workspace"
    nest = root / "wipe_me"
    nest.mkdir()
    (nest / "f.txt").write_text("z", encoding="utf-8")
    denied = files_ops.files_delete(str(nest), confirm=False, recursive=True, roots=[root])
    assert denied["ok"] is False
    monkeypatch.setenv("EXO_TRUST", "full")
    _ack()
    ok = files_ops.files_delete(str(nest), confirm=False, recursive=True, roots=[root])
    assert ok["ok"] is True


def test_registry_write_optional_in_full_trust(home, monkeypatch):
    denied = registry_ops.registry_write(
        r"HKCU\Software\ExoControlTrustTest", name="flag", value="1", confirm=False
    )
    assert denied["ok"] is False
    monkeypatch.setenv("EXO_TRUST", "full")
    _ack()
    # confirm_ok should pass; actual write may still fail off-Windows.
    assert confirm_ok(False, kind="registry_write") is True


def test_hklm_policy_lifted_in_full_trust(home, monkeypatch):
    monkeypatch.setenv("EXO_TRUST", "full")
    _ack()
    out = registry_ops.registry_write(
        r"HKLM\Software\ExoControlTrustTest", name="flag", value="1", confirm=True
    )
    # Policy no longer returns the old hard-deny. OS/access-denied is fine off-admin.
    assert "write denied" not in (out.get("error") or "").lower() or out.get("ok") is True


def test_anticheat_allowed_in_full_trust(home, monkeypatch):
    monkeypatch.setenv("EXO_TRUST", "full")
    _ack()
    out = infra_ops.kill_proc(name="EasyAntiCheat.exe", confirm=True)
    assert out.get("reason") != "protected_process"
    assert out.get("error") != "protected_process"


def test_protected_system_path_unlocked_in_full_trust(home, monkeypatch):
    monkeypatch.setenv("EXO_TRUST", "full")
    _ack()
    windir = Path(r"C:\Windows\System32\drivers")
    assert trust.is_protected_system_path(windir) is False
    # Kill file stays protected even in owner mode.
    kill = Path(trust.arm_kill_file()["path"])
    assert trust.is_protected_system_path(kill) is True


def test_kill_file_blocks_and_cannot_disarm(home, monkeypatch):
    armed = trust.arm_kill_file()
    assert armed["ok"] is True
    assert trust.human_kill_armed() is True
    gate = SafetyGate(SafetyConfig(min_action_interval_s=0.0))
    ok, why = gate.check("action", text="hi", confirm=True)
    assert ok is False
    assert "kill_switch" in why
    gate.disarm_kill_switch()
    ok2, _ = gate.check("action", text="hi", confirm=True)
    assert ok2 is False
    eng = ExoExecEngine()
    out = eng.execute([{"op": "disarm_kill_switch"}])
    assert out["steps"][0]["result"]["ok"] is False


def test_kill_env_blocks(home, monkeypatch):
    monkeypatch.setenv("EXO_KILL_SWITCH", "1")
    gate = SafetyGate(SafetyConfig(min_action_interval_s=0.0))
    ok, why = gate.check("action", confirm=True)
    assert ok is False
    assert "kill_switch" in why


def test_wipe_pattern_optional_in_full_trust(home, monkeypatch):
    monkeypatch.setenv("EXO_TRUST", "full")
    _ack()
    gate = SafetyGate(SafetyConfig(min_action_interval_s=0.0))
    ok, why = gate.check("action", text="format c:", confirm=False)
    assert ok is True, why


def test_identity_includes_trust(home):
    ident = identity()
    assert "trust" in ident["policy"]
    assert ident["policy"]["trust"]["level"] == "default"


def test_trust_status_op(home):
    eng = ExoExecEngine()
    out = eng.execute([{"op": "trust_status"}])
    assert out["ok"] is True
    res = out["steps"][0]["result"]
    assert res["ok"] is True
    assert res["level"] == "default"


def test_full_trust_widens_user_roots(home, monkeypatch):
    monkeypatch.setenv("EXO_TRUST", "full")
    _ack()
    extras = trust.extra_file_roots()
    assert extras
    assert any(Path.home() == p or str(Path.home()) in str(p) for p in extras)


def test_audit_log_written(home):
    _ack()
    path = trust.audit_path()
    assert path.is_file()
    text = path.read_text(encoding="utf-8")
    assert "full_trust_ack" in text
