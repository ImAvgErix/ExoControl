"""web_task structure planner and FakeBrowser execution."""
from __future__ import annotations

from aether.exec_engine import ExoExecEngine
from aether.web import parse_goal_actions, run_structure_actions, web_task


class FakeBrowser:
    def __init__(self):
        self.calls: list[str] = []
        self.url = "about:blank"
        self.title = ""

    def navigate(self, url, space_id=None, wait="domcontentloaded"):
        self.calls.append(f"nav:{url}")
        self.url = url
        self.title = "Example"
        return {"ok": True, "url": url, "title": self.title}

    def click(self, ref=None, selector=None, text=None, name=None, query=None, space_id=None, x=None, y=None):
        self.calls.append(f"click:{text or ref}")
        return {"ok": True, "text": text}

    def type_text(self, text, ref=None, selector=None, clear=False, space_id=None):
        self.calls.append(f"type:{text}")
        return {"ok": True, "text": text}

    def wait_for(self, text=None, selector=None, timeout=8, space_id=None, name=None, query=None):
        self.calls.append(f"wait:{text}")
        return {"ok": True, "text": text}

    def snapshot(self, space_id=None, include_screenshot=False):
        self.calls.append("snapshot")
        return {
            "ok": True,
            "title": self.title,
            "url": self.url,
            "elements": [{"ref": 0, "text": "More information"}],
            "text_sample": "Example Domain",
            "element_count": 1,
        }

    def extract(self, space_id=None, max_chars=4000):
        self.calls.append("extract")
        return {"ok": True, "title": self.title, "url": self.url, "text": "Example Domain"}

    def fill_form(self, fields, space_id=None):
        self.calls.append("fill")
        return {"ok": True, "fields": fields}

    def press(self, key, space_id=None):
        self.calls.append(f"press:{key}")
        return {"ok": True, "key": key}

    def scroll(self, dy=None, space_id=None, **kwargs):
        self.calls.append("scroll")
        return {"ok": True, "dy": dy}


def test_parse_goal_actions():
    acts = parse_goal_actions(
        'Go to https://example.com click "More information" then extract',
    )
    kinds = [a["action"] for a in acts]
    assert kinds[0] == "navigate"
    assert acts[0]["url"] == "https://example.com"
    assert "click" in kinds
    assert "extract" in kinds


def test_structure_actions_run(fake=None):
    browser = FakeBrowser()
    out = run_structure_actions(
        browser,
        [
            {"action": "navigate", "url": "https://example.com"},
            {"action": "click", "text": "More information"},
            {"action": "extract"},
        ],
    )
    assert out["ok"] is True
    assert out["mode"] == "structure"
    assert out["completed"] == 3
    assert "nav:https://example.com" in browser.calls
    assert out["extract"]


def test_web_task_auto_from_goal():
    browser = FakeBrowser()
    out = web_task(
        goal='open https://example.com and click "More information"',
        browser=browser,
        mode="structure",
    )
    assert out["ok"] is True
    assert any(c.startswith("nav:") for c in browser.calls)
    assert any(c.startswith("click:") for c in browser.calls)


def test_web_task_needs_plan_without_browser_use():
    out = web_task(goal="do something vague", mode="structure", browser=FakeBrowser())
    assert out["ok"] is False
    assert "parseable" in out["error"] or "actions" in out["error"]


def test_web_task_via_exec_requires_lease():
    eng = ExoExecEngine()
    out = eng.execute(
        [{"op": "web_task", "url": "https://example.com", "actions": [{"action": "extract"}]}]
    )
    assert out["steps"][0]["result"]["ok"] is False
    assert "lease" in out["steps"][0]["result"]["error"]


def test_web_task_via_exec_with_stub_browser(tmp_path, monkeypatch):
    monkeypatch.setenv("EXO_LOCK_DIR", str(tmp_path / "locks"))
    monkeypatch.setenv("EXO_STATE_DIR", str(tmp_path / "state"))
    eng = ExoExecEngine()
    fake = FakeBrowser()
    eng._get_browser = lambda: fake  # type: ignore[method-assign]
    out = eng.execute(
        [
            {"op": "lease_acquire", "agent_id": "web", "task": "example", "ttl_sec": 30},
            {
                "op": "web_task",
                "mode": "structure",
                "url": "https://example.com",
                "actions": [{"action": "extract"}],
            },
            {"op": "lease_release"},
        ]
    )
    assert out["ok"] is True
    res = out["steps"][1]["result"]
    assert res["ok"] is True
    assert res["mode"] == "structure"
    assert "extract" in fake.calls
