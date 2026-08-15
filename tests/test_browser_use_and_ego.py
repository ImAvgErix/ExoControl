"""Browser Use Cloud + ego lite honesty (Windows-only product)."""
from __future__ import annotations

import pytest

from aether.exec_engine import ExoExecEngine
from aether.ops_catalog import known_ops, lease_free_ops, lease_required_ops
from aether.policy import is_allowed_cdp_endpoint
from aether import browser_use_ops, ego_ops


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("EXO_LOCK_DIR", str(tmp_path / "locks"))
    monkeypatch.setenv("EXO_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("EXO_FILE_ROOTS", str(tmp_path / "workspace"))
    monkeypatch.setenv("EXO_LIVE_EYES", "0")
    (tmp_path / "workspace").mkdir()
    yield tmp_path


@pytest.fixture
def bu_key(monkeypatch):
    monkeypatch.setenv("BROWSER_USE_API_KEY", "bu_test_key")
    yield "bu_test_key"


def test_catalog_has_browser_use_and_ego():
    names = known_ops()
    for op in ("browser_use", "browser_use_start", "browser_use_stop", "browser_cloud", "ego"):
        assert op in names
    assert "ego_exec" not in names
    free = lease_free_ops()
    req = lease_required_ops()
    assert "browser_use" in free
    assert "ego" in free
    assert "browser_connect" in req


def test_browser_use_fails_closed_without_key(monkeypatch):
    monkeypatch.delenv("BROWSER_USE_API_KEY", raising=False)
    monkeypatch.delenv("EXO_BROWSER_USE_API_KEY", raising=False)
    out = browser_use_ops.run_task({"task": "Find HN"})
    assert out["ok"] is False
    assert out["code"] == "AUTHENTICATION"


def test_browser_use_creates_run(bu_key, monkeypatch):
    calls = []

    def fake(method, url, headers, payload, timeout):
        calls.append((method, url, payload))
        assert headers["X-Browser-Use-API-Key"] == "bu_test_key"
        return 201, {"id": "run-1", "sessionId": "sess-1", "status": "created"}, ""

    monkeypatch.setattr(browser_use_ops, "_REQUEST_JSON", fake)
    out = browser_use_ops.run_task({"task": "Find the top Show HN post"})
    assert out["ok"] is True
    assert out["run_id"] == "run-1"
    assert out["session_id"] == "sess-1"
    assert calls[0][0] == "POST"
    assert calls[0][1].endswith("/runs")
    assert calls[0][2]["task"] == "Find the top Show HN post"


def test_browser_use_polls_run_id(bu_key, monkeypatch):
    def fake(method, url, headers, payload, timeout):
        assert method == "GET"
        assert url.endswith("/runs/run-9")
        return 200, {"id": "run-9", "status": "completed", "output": "done"}, ""

    monkeypatch.setattr(browser_use_ops, "_REQUEST_JSON", fake)
    out = browser_use_ops.run_task({"run_id": "run-9"})
    assert out["ok"] is True
    assert out["status"] == "completed"
    assert out["output"] == "done"


def test_browser_use_start_and_stop(bu_key, monkeypatch):
    def fake(method, url, headers, payload, timeout):
        if method == "POST":
            assert payload["proxyCountryCode"] == "us"
            return 201, {
                "id": "br-1",
                "status": "active",
                "cdpUrl": "wss://connect.browser-use.com/cdp/tok",
                "liveUrl": "https://live.browser-use.com/br-1",
            }, ""
        assert method == "PATCH"
        assert url.endswith("/browsers/br-1")
        assert payload == {"action": "stop"}
        return 200, {"id": "br-1", "status": "stopped"}, ""

    monkeypatch.setattr(browser_use_ops, "_REQUEST_JSON", fake)
    started = browser_use_ops.start_browser({"country": "us"})
    assert started["ok"] is True
    assert started["id"] == "br-1"
    assert started["cdp_url"].startswith("wss://connect.browser-use.com/")
    stopped = browser_use_ops.stop_browser({"id": "br-1"})
    assert stopped["ok"] is True
    assert stopped["stopped"] is True


def test_browser_use_via_exec_is_lease_free(home, bu_key, monkeypatch):
    monkeypatch.setattr(
        browser_use_ops,
        "_REQUEST_JSON",
        lambda *a, **k: (201, {"id": "run-x", "status": "created"}, ""),
    )
    eng = ExoExecEngine()
    out = eng.execute([{"op": "browser_use", "task": "x"}])
    assert out["ok"] is True, out.get("last_error") or out
    assert out["steps"][0]["result"]["run_id"] == "run-x"


def test_browser_connect_provider_starts_then_attaches(home, bu_key, monkeypatch):
    monkeypatch.setattr(
        browser_use_ops,
        "_REQUEST_JSON",
        lambda *a, **k: (201, {
            "id": "br-9",
            "status": "active",
            "cdpUrl": "wss://connect.browser-use.com/cdp/z",
        }, ""),
    )

    class FakeBrowser:
        def __init__(self):
            self.endpoint = None

        def connect_cdp(self, endpoint, page_url=None, page_title=None):
            self.endpoint = endpoint
            return {"ok": True, "endpoint": endpoint, "space_id": "cdp-default"}

    class Stub:
        def status(self):
            return {"ok": True}

    eng = ExoExecEngine(controller=Stub())
    fake = FakeBrowser()
    eng._browser = fake
    out = eng.execute([
        {"op": "lease_acquire", "agent_id": "t", "task": "bu", "ttl_sec": 20, "eyes": False},
        {"op": "browser_connect", "provider": "browser-use"},
        {"op": "lease_release"},
    ])
    assert out["ok"] is True, out.get("last_error") or out
    step = next(s for s in out["steps"] if s["op"] == "browser_connect")
    assert step["result"]["ok"] is True
    assert step["result"]["provider"] == "browser-use"
    assert fake.endpoint == "wss://connect.browser-use.com/cdp/z"
    assert eng._browser_use_session == "br-9"


def test_browser_use_cdp_allowed_with_key(bu_key):
    assert is_allowed_cdp_endpoint("wss://connect.browser-use.com/cdp/z") is True
    assert is_allowed_cdp_endpoint("http://10.0.0.8:9222") is False


def test_ego_is_honest_windows_miss():
    info = ego_ops.detect()
    assert info["ok"] is True
    assert info["available"] is False
    assert info["ego_windows_ready"] is False
    assert info["exo_windows_only"] is True
    assert "Windows" in info["hint"]
    denied = ego_ops.exec_js({"js": "cliLog(1)"})
    assert denied["ok"] is False
    assert denied["code"] == "WINDOWS_ONLY"


def test_ego_via_exec(home):
    eng = ExoExecEngine()
    out = eng.execute([{"op": "ego"}])
    assert out["ok"] is True
    body = out["steps"][0]["result"]
    assert body["available"] is False
    assert body["ego_windows_ready"] is False


def test_status_reports_browser_use_and_ego(home, bu_key):
    eng = ExoExecEngine()
    out = eng.execute([{"op": "status"}])
    caps = out["steps"][0]["result"]["capabilities"]
    assert caps["browser_use"] is True
    assert caps["browser_use_configured"] is True
    assert caps["ego_lite"] is False
    assert caps["ego_windows_ready"] is False
