"""screenshot_on_miss must attach screenshot_base64 on structure-miss retry."""
from __future__ import annotations

from aether.exec_engine import AetherExecEngine


class FakeBrowser:
    def __init__(self):
        self.clicks = 0

    def click(self, **kwargs):
        self.clicks += 1
        if self.clicks == 1:
            return {"ok": False, "error": "no element matched"}
        return {"ok": True, "method": "ref"}

    def snapshot(self, space_id=None, include_screenshot=False):
        out = {"ok": True, "elements": [{"ref": "e1", "name": "Go"}], "url": "https://example.com"}
        if include_screenshot:
            out["screenshot_base64"] = "AAA"
        return out

    def screenshot(self, space_id=None):
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
