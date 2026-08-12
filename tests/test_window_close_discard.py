"""window_close should discard unsaved prompts (Don't save), not hang."""
from __future__ import annotations

from aether.smart import SmartController, ActionOutcome, Target


class _FakeCtrl(SmartController):
    """Minimal controller surface for unit-testing discard helpers."""

    def __init__(self):
        # Skip heavy SmartController init
        self._focus_pid = 1
        self._focus_window_id = 10
        self._calls = []

    def _window_alive(self, hwnd):
        # Simulate: alive until discard click
        return not getattr(self, "_gone", False)

    def _window_show(self, action, hwnd=None, cmd=None):
        self._calls.append(("show", action, hwnd))
        return {"ok": True, "action": action, "window_id": hwnd or 10}

    def _find_discard_button(self):
        if getattr(self, "_gone", False):
            return None
        return Target(kind="a11y", label="Don't save", confidence=0.95, source="test",
                      pid=1, window_id=10, element_index=0, x=1, y=1)

    def _deliver_click(self, target=None, button="left"):
        self._gone = True
        self._calls.append(("click", getattr(target, "label", None)))
        from aether.backends import DeliveryResult
        return DeliveryResult(ok=True, backend="test", message="clicked")

    def smart_hotkey(self, keys):
        self._calls.append(("hotkey", keys))
        return ActionOutcome(True, True, "ok")

    def smart_focus(self, **kwargs):
        return {"ok": True}


def test_window_close_clicks_dont_save():
    c = _FakeCtrl()
    out = c.window_close(hwnd=10, discard_unsaved=True, wait_gone=1.0)
    assert out["ok"] is True
    assert out.get("discard", {}).get("dismissed") is True
    assert out.get("discard", {}).get("label") == "Don't save"
    assert ("click", "Don't save") in c._calls


def test_window_close_can_skip_discard():
    c = _FakeCtrl()
    out = c.window_close(hwnd=10, discard_unsaved=False)
    assert out["ok"] is True
    assert "discard" not in out or out.get("discard") is None
    assert not any(x[0] == "click" for x in c._calls)
