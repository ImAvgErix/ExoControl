"""Wave 1 desk ops: Graph, Jina, git, GitHub, Windows desk, browser extras."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


@pytest.fixture
def tmp_roots(tmp_path, monkeypatch):
    monkeypatch.setenv("EXO_FILE_ROOTS", str(tmp_path))
    monkeypatch.setenv("EXO_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("EXO_LOCK_DIR", str(tmp_path / "locks"))
    monkeypatch.setenv("EXO_LIVE_EYES", "0")
    (tmp_path / "state").mkdir()
    (tmp_path / "locks").mkdir()
    return tmp_path


def _engine():
    from exo_control.exec_engine import ExoExecEngine
    return ExoExecEngine()


def _result(script, eng=None):
    out = (eng or _engine()).execute(script if isinstance(script, list) else [script])
    return out["steps"][0]["result"]


# ---------------------------------------------------------------------------
# Catalog / capabilities
# ---------------------------------------------------------------------------

def test_wave1_catalog_lease_flags():
    from exo_control.ops_catalog import get_op

    lease_free = [
        "xlsx", "todo", "onenote", "teams", "mail_send",
        "volume", "winget", "recycle", "eventlog",
        "ocr_win", "stt", "tts", "read_url", "git", "gh_pr",
    ]
    lease_on = ["window_move", "browser_network", "browser_downloads", "browser_pdf", "browser_tabs"]
    for name in lease_free:
        spec = get_op(name)
        assert spec is not None, name
        assert spec.get("lease") is False, name
    for name in lease_on:
        spec = get_op(name)
        assert spec is not None, name
        assert spec.get("lease") is True, name


def test_wave1_capabilities_keys():
    from exo_control.addon_ops import capabilities
    caps = capabilities()
    for key in (
        "graph", "jina", "git", "github", "volume", "winget",
        "recycle", "eventlog", "ocr_win", "stt", "tts",
    ):
        assert key in caps, key


def test_wave1_aether_shims():
    import aether.graph_ops as g
    import aether.jina_ops as j
    import aether.git_ops as gi
    import aether.github_ops as gh
    import aether.win_desk_ops as w
    assert g.__name__ == "exo_control.graph_ops"
    assert j.__name__ == "exo_control.jina_ops"
    assert gi.__name__ == "exo_control.git_ops"
    assert gh.__name__ == "exo_control.github_ops"
    assert w.__name__ == "exo_control.win_desk_ops"


# ---------------------------------------------------------------------------
# xlsx — local CSV under allowroots
# ---------------------------------------------------------------------------

def test_xlsx_reads_local_csv_range(tmp_roots):
    csv_path = tmp_roots / "sheet.csv"
    csv_path.write_text("a,b,c\n1,2,3\n4,5,6\n", encoding="utf-8")
    out = _result({"op": "xlsx", "path": str(csv_path), "range": "A1:B2"})
    assert out["ok"] is True
    assert out["rows"] == [["a", "b"], ["1", "2"]]
    assert out.get("source") == "local"


def test_xlsx_outside_root_denied(tmp_path, monkeypatch):
    monkeypatch.setenv("EXO_FILE_ROOTS", str(tmp_path / "allowed"))
    (tmp_path / "allowed").mkdir()
    outside = tmp_path / "secret.csv"
    outside.write_text("x,y\n", encoding="utf-8")
    out = _result({"op": "xlsx", "path": str(outside)})
    assert out["ok"] is False
    assert "allowroot" in out.get("error", "").lower() or out.get("outside") is True


# ---------------------------------------------------------------------------
# Graph — todo / onenote / teams / mail_send
# ---------------------------------------------------------------------------

def test_todo_lists_via_graph(monkeypatch):
    monkeypatch.setenv("MICROSOFT_GRAPH_TOKEN", "tok")
    import exo_control.graph_ops as g

    def fake(method, url, headers, payload, timeout):
        assert "todo/lists" in url
        return 200, {"value": [{"id": "1", "displayName": "Tasks"}]}, ""

    monkeypatch.setattr(g, "_REQUEST_JSON", fake)
    out = _result({"op": "todo"})
    assert out["ok"] is True
    assert out["lists"][0]["displayName"] == "Tasks"


def test_onenote_and_teams_via_graph(monkeypatch):
    monkeypatch.setenv("EXO_GRAPH_TOKEN", "tok")
    import exo_control.graph_ops as g
    seen: List[str] = []

    def fake(method, url, headers, payload, timeout):
        seen.append(url)
        if "onenote" in url:
            return 200, {"value": [{"id": "nb", "displayName": "Work"}]}, ""
        return 200, {"value": [{"id": "t", "displayName": "Eng"}]}, ""

    monkeypatch.setattr(g, "_REQUEST_JSON", fake)
    notes = _result({"op": "onenote"})
    teams = _result({"op": "teams"})
    assert notes["ok"] and notes["notebooks"][0]["displayName"] == "Work"
    assert teams["ok"] and teams["teams"][0]["displayName"] == "Eng"
    assert any("onenote" in u for u in seen)
    assert any("joinedTeams" in u or "/me/chats" in u for u in seen)


def test_mail_send_requires_confirm(monkeypatch):
    monkeypatch.setenv("AZURE_TOKEN", "tok")
    import exo_control.graph_ops as g
    monkeypatch.setattr(g, "_REQUEST_JSON", lambda *a, **k: (202, {}, ""))
    denied = _result({"op": "mail_send", "to": "a@b.com", "subject": "hi", "body": "x"})
    assert denied["ok"] is False
    assert "confirm" in denied.get("error", "").lower()

    sent = _result({
        "op": "mail_send",
        "to": "a@b.com",
        "subject": "hi",
        "body": "x",
        "confirm": True,
    })
    assert sent["ok"] is True


def test_graph_ops_fail_closed_without_token(monkeypatch):
    monkeypatch.delenv("MICROSOFT_GRAPH_TOKEN", raising=False)
    monkeypatch.delenv("EXO_GRAPH_TOKEN", raising=False)
    monkeypatch.delenv("AZURE_TOKEN", raising=False)
    monkeypatch.delenv("GRAPH_TOKEN", raising=False)
    out = _result({"op": "todo"})
    assert out["ok"] is False
    assert out.get("code") == "AUTHENTICATION"


# ---------------------------------------------------------------------------
# Jina read_url
# ---------------------------------------------------------------------------

def test_read_url_jina(monkeypatch):
    import exo_control.jina_ops as j

    def fake(method, url, headers, timeout):
        assert url.startswith("https://r.jina.ai/")
        return 200, "# Hello\nworld", ""

    monkeypatch.setattr(j, "_REQUEST_TEXT", fake)
    out = _result({"op": "read_url", "url": "https://example.com/doc"})
    assert out["ok"] is True
    assert "Hello" in out["markdown"]
    assert out.get("provider") == "jina"


# ---------------------------------------------------------------------------
# git / gh_pr
# ---------------------------------------------------------------------------

def test_git_status_allowrooted(tmp_roots):
    repo = tmp_roots / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t.test"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=repo, check=True, capture_output=True)
    (repo / "a.txt").write_text("hi\n", encoding="utf-8")
    out = _result({"op": "git", "path": str(repo), "action": "status"})
    assert out["ok"] is True
    assert "a.txt" in out.get("stdout", "") or out.get("dirty") is True


def test_gh_pr_via_github_api(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_test")
    import exo_control.github_ops as gh

    def fake(method, url, headers, payload, timeout):
        assert "pulls/7" in url
        return 200, {"number": 7, "title": "Wave", "state": "open"}, ""

    monkeypatch.setattr(gh, "_REQUEST_JSON", fake)
    out = _result({"op": "gh_pr", "repo": "ImAvgErix/ExoControl", "number": 7})
    assert out["ok"] is True
    assert out["pr"]["title"] == "Wave"


# ---------------------------------------------------------------------------
# Windows desk — hooks so Linux CI stays green
# ---------------------------------------------------------------------------

def test_volume_get_via_hook(monkeypatch):
    import exo_control.win_desk_ops as w
    monkeypatch.setattr(
        w, "_IMPL",
        lambda op, step: {"ok": True, "muted": False, "level": 40} if op == "volume" else None,
    )
    out = _result({"op": "volume"})
    assert out["ok"] is True
    assert out["level"] == 40


def test_volume_set_requires_confirm(monkeypatch):
    import exo_control.win_desk_ops as w
    monkeypatch.setattr(w, "_IMPL", lambda op, step: {"ok": True, "level": 10})
    denied = _result({"op": "volume", "level": 10})
    assert denied["ok"] is False
    assert "confirm" in denied.get("error", "").lower()
    ok = _result({"op": "volume", "level": 10, "confirm": True})
    assert ok["ok"] is True


def test_winget_recycle_eventlog_hooks(monkeypatch):
    import exo_control.win_desk_ops as w

    def impl(op, step):
        if op == "winget":
            return {"ok": True, "packages": [{"id": "Git.Git"}]}
        if op == "recycle":
            return {"ok": True, "items": [{"name": "old.txt"}]}
        if op == "eventlog":
            return {"ok": True, "events": [{"id": 1000, "log": "Application"}]}
        return None

    monkeypatch.setattr(w, "_IMPL", impl)
    assert _result({"op": "winget", "query": "git"})["packages"][0]["id"] == "Git.Git"
    assert _result({"op": "recycle"})["items"][0]["name"] == "old.txt"
    assert _result({"op": "eventlog", "log": "Application"})["events"][0]["id"] == 1000


def test_recycle_empty_requires_confirm(monkeypatch):
    import exo_control.win_desk_ops as w
    monkeypatch.setattr(w, "_IMPL", lambda op, step: {"ok": True, "emptied": True})
    denied = _result({"op": "recycle", "action": "empty"})
    assert denied["ok"] is False
    ok = _result({"op": "recycle", "action": "empty", "confirm": True})
    assert ok["ok"] is True


def test_ocr_stt_tts_hooks(monkeypatch):
    import exo_control.win_desk_ops as w

    def impl(op, step):
        if op == "ocr_win":
            return {"ok": True, "text": "hello"}
        if op == "stt":
            return {"ok": True, "text": "spoken"}
        if op == "tts":
            return {"ok": True, "spoke": True}
        return None

    monkeypatch.setattr(w, "_IMPL", impl)
    assert _result({"op": "ocr_win", "path": "x.png"})["text"] == "hello"
    assert _result({"op": "stt"})["text"] == "spoken"
    assert _result({"op": "tts", "text": "hi"})["spoke"] is True


def test_win_desk_unavailable_without_hook_on_linux(monkeypatch):
    if sys.platform == "win32":
        pytest.skip("Windows has native impl")
    import exo_control.win_desk_ops as w
    monkeypatch.setattr(w, "_IMPL", None)
    out = _result({"op": "volume"})
    assert out["ok"] is False
    assert out.get("code") in {"WINDOWS_ONLY", "UNAVAILABLE"}


# ---------------------------------------------------------------------------
# window_move — lease + stub controller
# ---------------------------------------------------------------------------

def test_window_move_requires_lease(tmp_roots):
    out = _result({"op": "window_move", "x": 10, "y": 10})
    assert out["ok"] is False
    assert "lease" in out.get("error", "").lower()


def test_window_move_via_controller(tmp_roots):
    from exo_control.exec_engine import ExoExecEngine

    class Stub:
        def status(self):
            return {"ok": True}

        def window_move(self, hwnd=None, **kw):
            return {"ok": True, "moved": True, "x": kw.get("x"), "y": kw.get("y")}

    eng = ExoExecEngine(controller=Stub())
    out = eng.execute([
        {"op": "lease_acquire", "agent_id": "t", "task": "move", "ttl_sec": 30},
        {"op": "window_move", "x": 20, "y": 40, "w": 800, "h": 600},
        {"op": "lease_release"},
    ])
    assert out["steps"][1]["result"]["ok"] is True
    assert out["steps"][1]["result"]["x"] == 20


# ---------------------------------------------------------------------------
# Browser extras — FakeBrowser + lease
# ---------------------------------------------------------------------------

class FakeBrowser:
    def __init__(self) -> None:
        self._network: List[Dict[str, Any]] = [
            {"url": "https://api.example.com/v1", "method": "GET", "status": 200},
        ]
        self._downloads: List[Dict[str, Any]] = [
            {"url": "https://example.com/a.zip", "suggested_filename": "a.zip"},
        ]

    def network_log(self, space_id=None, max_items=40):
        return {"ok": True, "requests": self._network[:max_items]}

    def downloads(self, space_id=None, max_items=20):
        return {"ok": True, "downloads": self._downloads[:max_items]}

    def pdf(self, path: str, space_id=None):
        return {"ok": True, "path": path, "bytes": 14}

    def tabs(self, space_id=None, index=None, url=None):
        tabs = [{"index": 0, "url": "https://example.com/app", "space_id": "default"}]
        if index is not None or url:
            return {"ok": True, "tabs": tabs, "active": tabs[0]}
        return {"ok": True, "tabs": tabs}


def test_browser_extras_need_lease(tmp_roots):
    for op in ("browser_network", "browser_downloads", "browser_pdf", "browser_tabs"):
        out = _result({"op": op})
        assert out["ok"] is False
        assert "lease" in out.get("error", "").lower()


def test_browser_extras_via_fake(tmp_roots):
    from exo_control.exec_engine import ExoExecEngine

    class Stub:
        def status(self):
            return {"ok": True}

    eng = ExoExecEngine(controller=Stub())
    eng._browser = FakeBrowser()
    pdf_path = str(tmp_roots / "page.pdf")
    out = eng.execute([
        {"op": "lease_acquire", "agent_id": "t", "task": "br", "ttl_sec": 30},
        {"op": "browser_network"},
        {"op": "browser_downloads"},
        {"op": "browser_pdf", "path": pdf_path},
        {"op": "browser_tabs"},
        {"op": "lease_release"},
    ])
    net, dls, pdf, tabs = (out["steps"][i]["result"] for i in (1, 2, 3, 4))
    assert net["ok"] and net["requests"][0]["status"] == 200
    assert dls["ok"] and dls["downloads"][0]["suggested_filename"] == "a.zip"
    assert pdf["ok"] and Path(pdf["path"]).resolve() == Path(pdf_path).resolve()
    assert tabs["ok"] and tabs["tabs"][0]["url"].startswith("https://")
