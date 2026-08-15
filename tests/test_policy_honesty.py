"""1.3 honesty: lease token hidden, force gated, files roots, env redact, confirm parse."""
from __future__ import annotations

import os

import pytest

from aether import desktop_lease, files_ops, infra_ops
from aether.exec_engine import ExoExecEngine
from aether.policy import is_loopback_endpoint, parse_confirm, sanitize_cdp_endpoints
from aether.safety import SafetyConfig, SafetyGate


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("EXO_LOCK_DIR", str(tmp_path / "locks"))
    monkeypatch.setenv("EXO_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("EXO_FILE_ROOTS", str(tmp_path / "workspace"))
    (tmp_path / "workspace").mkdir()
    yield tmp_path


def test_parse_confirm_rejects_string_false():
    assert parse_confirm("false") is False
    assert parse_confirm("true") is True
    assert parse_confirm(True) is True
    assert parse_confirm(1) is True
    assert parse_confirm("yes") is True
    assert parse_confirm(None) is False


def test_status_hides_token(home):
    acq = desktop_lease.acquire("alpha", "hold", ttl_sec=30)
    st = desktop_lease.status()
    assert st["held"] is True
    assert "token" not in st
    assert st.get("has_token") is True
    desktop_lease.release(acq["token"])


def test_same_agent_renews(home):
    a = desktop_lease.acquire("solo", "one", ttl_sec=30)
    b = desktop_lease.acquire("solo", "two", ttl_sec=30)
    assert b["ok"] is True
    assert b.get("renewed") is True
    assert b["token"] == a["token"]
    desktop_lease.release(a["token"])


def test_force_release_needs_holder_or_env(home, monkeypatch):
    monkeypatch.delenv("EXO_ALLOW_FORCE_RELEASE", raising=False)
    a = desktop_lease.acquire("sticky", "x", ttl_sec=60)
    denied = desktop_lease.force_release()
    assert denied["ok"] is False
    assert "EXO_ALLOW_FORCE_RELEASE" in denied["error"]
    assert desktop_lease.status()["held"] is True
    ok = desktop_lease.force_release(agent_id="sticky")
    assert ok["ok"] is True
    assert desktop_lease.status()["held"] is False
    # leftover token must not work
    assert a["token"]


def test_force_release_operator_env(home, monkeypatch):
    monkeypatch.setenv("EXO_ALLOW_FORCE_RELEASE", "1")
    desktop_lease.acquire("x", "y", ttl_sec=60)
    out = desktop_lease.force_release()
    assert out["ok"] is True
    assert out.get("reason") == "operator"


def test_files_confirm_does_not_unlock_roots(home):
    secret = home / "secret.txt"
    secret.write_text("nope", encoding="utf-8")
    out = files_ops.files_read(str(secret), confirm=True, roots=[home / "workspace"])
    assert out["ok"] is False
    assert "EXO_ALLOW_OUTSIDE_ROOTS" in out["error"]


def test_files_operator_outside(home, monkeypatch):
    monkeypatch.setenv("EXO_ALLOW_OUTSIDE_ROOTS", "1")
    secret = home / "secret.txt"
    secret.write_text("ok", encoding="utf-8")
    out = files_ops.files_read(str(secret), confirm=True, roots=[home / "workspace"])
    assert out["ok"] is True
    assert out["text"] == "ok"


def test_kill_unresolved_pid_fail_closed(monkeypatch):
    monkeypatch.setattr(infra_ops, "_proc_name_for_pid", lambda pid: "")
    out = infra_ops.kill_proc(4242, confirm=True)
    assert out["ok"] is False
    assert out.get("reason") == "unresolved_process"


def test_env_get_redacts_secrets(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-secret")
    monkeypatch.delenv("EXO_ALLOW_ENV_VALUES", raising=False)
    out = infra_ops.env_get("OPENAI_API_KEY")
    assert out["ok"] is True
    assert out.get("redacted") is True
    assert out.get("value") is None
    monkeypatch.setenv("EXO_ALLOW_ENV_VALUES", "1")
    shown = infra_ops.env_get("OPENAI_API_KEY")
    assert shown["value"] == "sk-secret"


def test_cdp_loopback_and_sanitize():
    from aether.policy import is_allowed_cdp_endpoint, is_browser_use_cdp

    assert is_loopback_endpoint("http://127.0.0.1:9222")
    assert is_loopback_endpoint("http://localhost:9229")
    assert not is_loopback_endpoint("http://10.0.0.8:9222")
    assert is_browser_use_cdp("wss://connect.browser-use.com/cdp/abc")
    assert not is_browser_use_cdp("wss://evil.example/cdp")
    assert is_allowed_cdp_endpoint("http://127.0.0.1:9222")
    assert not is_allowed_cdp_endpoint("wss://connect.browser-use.com/cdp/abc")
    clean = sanitize_cdp_endpoints([
        {
            "endpoint": "http://127.0.0.1:9222",
            "ws": "ws://127.0.0.1:9222/devtools",
            "targets": [{"webSocketDebuggerUrl": "ws://x", "url": "https://a"}],
        }
    ])
    assert "ws" not in clean[0]
    assert "webSocketDebuggerUrl" not in clean[0]["targets"][0]


def test_format_string_is_not_destructive():
    g = SafetyGate(SafetyConfig(min_action_interval_s=0.0))
    ok, _ = g.check("action", text="print a format string", confirm=False)
    assert ok is True


def test_screenshot_requires_lease(home):
    class Stub:
        def status(self):
            return {"ok": True}

        def window_state(self, _):
            return {"known": False}

        @property
        def perception(self):
            class P:
                def capture(self, monitor=1, region=None):
                    return None
            return P()

        _focus_window_id = None

    eng = ExoExecEngine(controller=Stub())
    denied = eng.screenshot_checked()
    assert denied["ok"] is False
    assert "lease" in denied["error"]


def test_help_default_is_compact():
    from aether.ops_catalog import CORE_OPS, list_ops

    compact = list_ops()
    assert compact["compact"] is True
    assert compact["count"] == len(CORE_OPS)
    full = list_ops(detail=True)
    assert full["compact"] is False
    assert full["count"] >= 40


def test_catalog_lease_sets_cover_cursor_and_notify():
    from aether.ops_catalog import lease_free_ops, lease_required_ops

    req = lease_required_ops()
    free = lease_free_ops()
    assert "notify" in req
    assert "cursor_exec" in req
    assert "screenshot" in req
    assert "lease_status" in free
    assert "help" in free
    assert "search" in free
    assert "search_content" in free
    assert "browser_use" in free
    assert "ego" in free
    assert "browser_connect" in req
    assert not (req & free)


def test_browser_eval_requires_confirm(home):
    class Stub:
        def status(self):
            return {"ok": True}

    class FakeBrowser:
        def evaluate(self, js, space_id=None):
            return {"ok": True, "value": "x"}

    eng = ExoExecEngine(controller=Stub())
    eng._browser = FakeBrowser()
    out = eng.execute([
        {"op": "lease_acquire", "agent_id": "b", "task": "eval", "ttl_sec": 30},
        {"op": "browser_eval", "js": "1+1"},
        {"op": "lease_release"},
    ])
    assert out["steps"][1]["result"]["ok"] is False
    assert "confirm" in out["steps"][1]["result"]["error"]
