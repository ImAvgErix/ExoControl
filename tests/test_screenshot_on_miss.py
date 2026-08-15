"""screenshot_on_miss attaches a shot only when True; default miss stays screenshot-free."""
from __future__ import annotations

from aether.exec_engine import AetherExecEngine


class FakeBrowser:
    def __init__(self):
        self.clicks = 0
        self.screenshot_calls = 0
        self.snapshot_include_screenshot = []

    def click(self, **kwargs):
        self.clicks += 1
        if self.clicks == 1:
            return {"ok": False, "error": "no element matched"}
        return {"ok": True, "method": "ref"}

    def snapshot(self, space_id=None, include_screenshot=False):
        self.snapshot_include_screenshot.append(include_screenshot)
        out = {"ok": True, "elements": [{"ref": "e1", "name": "Go"}], "url": "https://example.com"}
        if include_screenshot:
            out["screenshot_base64"] = "AAA"
        return out

    def screenshot(self, space_id=None):
        self.screenshot_calls += 1
        return {"ok": True, "screenshot_base64": "YmFzZTY0c2hvdA==", "bytes": 12}


def test_screenshot_on_miss_attaches_base64(tmp_path, monkeypatch):
    monkeypatch.setenv("AETHER_LOCK_DIR", str(tmp_path / "locks"))
    monkeypatch.setenv("AETHER_STATE_DIR", str(tmp_path / "state"))
    eng = AetherExecEngine()
    browser = FakeBrowser()
    monkeypatch.setattr(eng, "_get_browser", lambda: browser)
    eng.execute([{"op": "lease_acquire", "agent": "t", "task": "miss", "ttl_sec": 30}])
    out = eng.execute(
        [
            {
                "op": "browser_click",
                "ref": "missing",
                "screenshot_on_miss": True,
            }
        ]
    )
    res = out["steps"][0]["result"]
    assert res.get("structure_miss_retry") is True
    assert res.get("screenshot_base64") == "YmFzZTY0c2hvdA=="
    assert isinstance(res.get("miss_screenshot"), dict)
    assert res["miss_screenshot"].get("screenshot_base64")


def _run_structure_miss(tmp_path, monkeypatch, step):
    monkeypatch.setenv("AETHER_LOCK_DIR", str(tmp_path / "locks"))
    monkeypatch.setenv("AETHER_STATE_DIR", str(tmp_path / "state"))
    eng = AetherExecEngine()
    browser = FakeBrowser()
    monkeypatch.setattr(eng, "_get_browser", lambda: browser)
    eng.execute([{"op": "lease_acquire", "agent": "t", "task": "miss", "ttl_sec": 30}])
    out = eng.execute([step])
    return out["steps"][0]["result"], browser


def _assert_structure_miss_has_no_screenshot(res, browser):
    assert res.get("structure_miss_retry") is True
    assert not res.get("screenshot_base64")
    assert not res.get("miss_screenshot")
    assert browser.screenshot_calls == 0
    snap = res.get("snapshot") or {}
    assert not snap.get("screenshot_base64")
    assert browser.snapshot_include_screenshot
    assert all(flag is False for flag in browser.snapshot_include_screenshot)


def test_default_structure_miss_has_no_screenshot(tmp_path, monkeypatch):
    res, browser = _run_structure_miss(
        tmp_path,
        monkeypatch,
        {"op": "browser_click", "ref": "missing"},
    )
    _assert_structure_miss_has_no_screenshot(res, browser)


def test_screenshot_on_miss_false_has_no_screenshot(tmp_path, monkeypatch):
    res, browser = _run_structure_miss(
        tmp_path,
        monkeypatch,
        {"op": "browser_click", "ref": "missing", "screenshot_on_miss": False},
    )
    _assert_structure_miss_has_no_screenshot(res, browser)
