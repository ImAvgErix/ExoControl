from aether.smart import SmartController


class _FocusStub(SmartController):
    def __init__(self):
        # bypass heavy init
        self._focus_pid = None
        self._focus_window_id = None
        self._metrics = {}
        class _Macros:
            def is_recording(self):
                return False
            def add(self, *a, **k):
                return None
        self.macros = _Macros()

    def list_windows(self):
        return [
            {"title": "Exo Launcher", "pid": 2, "handle": 20, "class_name": "Chrome_WidgetWin_1", "visible": True, "minimized": False},
            {"title": "Exo Launcher", "pid": 1, "handle": 10, "class_name": "WinUIDesktopWin32WindowClass", "visible": True, "minimized": False},
        ]

    def focus_window(self, pid, window_id=None):
        self._focus_pid = pid
        self._focus_window_id = window_id
        return {"ok": True, "pid": pid, "window_id": window_id, "raised": True}


def test_smart_focus_prefers_winui_host_over_webview():
    c = _FocusStub()
    result = c.smart_focus(title="Exo Launcher")
    assert result["ok"] is True
    assert result["pid"] == 1
    assert result["window_id"] == 10
