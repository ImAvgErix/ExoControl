"""Remaining waves 3–5: Graph writes, CDP extras, open data, SaaS, files/sys."""
from __future__ import annotations

import sqlite3
import sys
import zipfile
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


LEASE_FREE = [
    "cal_add", "todo_add", "contacts", "drive_put", "mail_reply",
    "ddg", "wiki", "weather", "rss", "hn", "arxiv",
    "jira", "discord", "airtable", "trello", "asana", "gh_issue", "telegram", "serper", "brave",
    "zip", "unzip", "files_mkdir", "files_stat", "tree", "diff_files",
    "sqlite", "pdf_info", "image_info", "b64",
    "which", "now", "uuid_gen", "ports", "ip_addr", "ping", "dns", "uptime",
    "brightness", "lock_pc", "idle", "usb", "bluetooth", "printers",
    "bitlocker", "defender", "win_updates", "fonts", "dark_mode",
]
LEASE_ON = [
    "browser_back", "browser_forward", "browser_reload", "browser_select",
    "browser_upload", "browser_dialog", "browser_storage", "browser_cookies",
    "browser_console", "browser_viewport",
]
CAP_KEYS = [
    "open_data", "saas2", "files_plus", "sys_plus",
    "ddg", "wiki", "jira", "discord", "zip", "sqlite", "which", "lock_pc",
]


def test_wave35_catalog_lease_flags():
    from exo_control.ops_catalog import get_op
    for name in LEASE_FREE:
        spec = get_op(name)
        assert spec is not None, name
        assert spec.get("lease") is False, name
    for name in LEASE_ON:
        spec = get_op(name)
        assert spec is not None, name
        assert spec.get("lease") is True, name


def test_wave35_capabilities_and_shims():
    from exo_control.addon_ops import capabilities
    caps = capabilities()
    for key in CAP_KEYS:
        assert key in caps, key
    import aether.open_data_ops as o
    import aether.saas2_ops as s
    import aether.files_plus_ops as f
    import aether.sys_plus_ops as y
    assert o.__name__ == "exo_control.open_data_ops"
    assert s.__name__ == "exo_control.saas2_ops"
    assert f.__name__ == "exo_control.files_plus_ops"
    assert y.__name__ == "exo_control.sys_plus_ops"


def test_graph_writes_need_confirm(monkeypatch):
    monkeypatch.setenv("MICROSOFT_GRAPH_TOKEN", "tok")
    import exo_control.graph_ops as g
    monkeypatch.setattr(g, "_REQUEST_JSON", lambda *a, **k: (201, {"id": "e1"}, ""))
    assert _result({"op": "cal_add", "subject": "Standup"})["ok"] is False
    assert _result({"op": "cal_add", "subject": "Standup", "confirm": True})["ok"] is True
    assert _result({"op": "todo_add", "title": "Ship", "list": "1"})["ok"] is False
    assert _result({"op": "todo_add", "title": "Ship", "list": "1", "confirm": True})["ok"] is True
    assert _result({"op": "mail_reply", "id": "m1", "body": "ok"})["ok"] is False
    assert _result({"op": "mail_reply", "id": "m1", "body": "ok", "confirm": True})["ok"] is True


def test_contacts_and_drive_put(tmp_roots, monkeypatch):
    monkeypatch.setenv("EXO_GRAPH_TOKEN", "tok")
    import exo_control.graph_ops as g

    def fake(method, url, headers, payload, timeout):
        if "contacts" in url:
            return 200, {"value": [{"displayName": "Ada", "id": "c1"}]}, ""
        return 201, {"id": "item1", "name": "a.txt"}, ""

    monkeypatch.setattr(g, "_REQUEST_JSON", fake)
    contacts = _result({"op": "contacts"})
    assert contacts["ok"] and contacts["contacts"][0]["displayName"] == "Ada"
    src = tmp_roots / "a.txt"
    src.write_text("hi", encoding="utf-8")
    denied = _result({"op": "drive_put", "path": str(src), "dest": "a.txt"})
    assert denied["ok"] is False
    put = _result({"op": "drive_put", "path": str(src), "dest": "a.txt", "confirm": True})
    assert put["ok"] is True


def test_open_data_http(monkeypatch):
    import exo_control.open_data_ops as o

    def fake(method, url, headers, payload, timeout):
        if "duckduckgo" in url:
            return 200, {"AbstractText": "A duck", "RelatedTopics": []}, ""
        if "wikipedia" in url:
            return 200, {"value": ["q", ["Ada"], ["bio"], ["https://w/Ada"]]}, ""
        if "open-meteo" in url and "geocoding" in url:
            return 200, {"results": [{"latitude": 1.0, "longitude": 2.0, "name": "X"}]}, ""
        if "open-meteo" in url:
            return 200, {"current": {"temperature_2m": 21}}, ""
        if "algolia" in url:
            return 200, {"hits": [{"title": "Show HN", "url": "https://x"}]}, ""
        if "arxiv" in url:
            return 200, {}, "<entry><title>Paper</title></entry>"
        return 200, {"items": [{"title": "Feed"}]}, ""

    monkeypatch.setattr(o, "_REQUEST_JSON", fake)
    monkeypatch.setattr(o, "_REQUEST_TEXT", lambda *a, **k: (200, "<item><title>Feed</title></item>", ""))
    assert _result({"op": "ddg", "query": "duck"})["ok"]
    assert _result({"op": "wiki", "query": "Ada"})["results"][0]["title"] == "Ada"
    assert _result({"op": "weather", "city": "X"})["ok"]
    assert _result({"op": "hn", "query": "show"})["hits"][0]["title"] == "Show HN"
    assert _result({"op": "rss", "url": "https://example.com/feed.xml"})["ok"]
    assert _result({"op": "arxiv", "query": "transformers"})["ok"]


def test_saas2_and_gh_issue(monkeypatch):
    monkeypatch.setenv("JIRA_BASE", "https://ex.example.atlassian.net")
    monkeypatch.setenv("JIRA_EMAIL", "a@b.com")
    monkeypatch.setenv("JIRA_API_TOKEN", "jt")
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "dt")
    monkeypatch.setenv("AIRTABLE_API_KEY", "at")
    monkeypatch.setenv("TRELLO_KEY", "tk")
    monkeypatch.setenv("TRELLO_TOKEN", "tt")
    monkeypatch.setenv("ASANA_ACCESS_TOKEN", "as")
    monkeypatch.setenv("GITHUB_TOKEN", "gh")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tg")
    monkeypatch.setenv("SERPER_API_KEY", "sp")
    monkeypatch.setenv("BRAVE_API_KEY", "br")
    import exo_control.saas2_ops as s
    import exo_control.github_ops as gh

    def fake(method, url, headers, payload, timeout):
        if "atlassian" in url:
            return 200, {"issues": [{"key": "ENG-1", "fields": {"summary": "Bug"}}]}, ""
        if "discord" in url:
            return 200, {"id": "1", "username": "bot"}, ""
        if "airtable" in url:
            return 200, {"records": [{"id": "rec1"}]}, ""
        if "trello" in url:
            return 200, {"value": [{"name": "Board", "id": "b1"}]}, ""
        if "asana" in url:
            return 200, {"data": [{"gid": "1", "name": "Task"}]}, ""
        if "serper" in url:
            return 200, {"organic": [{"title": "S", "link": "https://s"}]}, ""
        if "brave" in url:
            return 200, {"web": {"results": [{"title": "B", "url": "https://b"}]}}, ""
        if "telegram" in url:
            return 200, {"ok": True, "result": {"message_id": 9}}, ""
        return 200, {}, ""

    monkeypatch.setattr(s, "_REQUEST_JSON", fake)
    monkeypatch.setattr(gh, "_REQUEST_JSON", lambda *a, **k: (200, [{"number": 3, "title": "Hi", "state": "open"}], ""))
    assert _result({"op": "jira", "jql": "project=ENG"})["issues"][0]["key"] == "ENG-1"
    assert _result({"op": "discord"})["ok"]
    assert _result({"op": "airtable", "base": "app1", "table": "T"})["records"][0]["id"] == "rec1"
    assert _result({"op": "trello"})["ok"]
    assert _result({"op": "asana"})["ok"]
    assert _result({"op": "gh_issue", "repo": "ImAvgErix/ExoControl"})["issues"][0]["number"] == 3
    assert _result({"op": "serper", "query": "x"})["ok"]
    assert _result({"op": "brave", "query": "x"})["ok"]
    denied = _result({"op": "telegram", "chat_id": "1", "text": "hi"})
    assert denied["ok"] is False
    assert _result({"op": "telegram", "chat_id": "1", "text": "hi", "confirm": True})["ok"]


def test_files_plus_local(tmp_roots):
    src = tmp_roots / "n.txt"
    src.write_text("alpha\n", encoding="utf-8")
    other = tmp_roots / "o.txt"
    other.write_text("beta\n", encoding="utf-8")
    mkdir = _result({"op": "files_mkdir", "path": str(tmp_roots / "sub")})
    assert mkdir["ok"] and (tmp_roots / "sub").is_dir()
    st = _result({"op": "files_stat", "path": str(src)})
    assert st["ok"] and st["is_file"] is True
    tree = _result({"op": "tree", "path": str(tmp_roots)})
    assert tree["ok"] and tree["entries"]
    diff = _result({"op": "diff_files", "a": str(src), "b": str(other)})
    assert diff["ok"] and diff.get("changed") is True
    zpath = tmp_roots / "pack.zip"
    zipped = _result({"op": "zip", "path": str(src), "dest": str(zpath)})
    assert zipped["ok"] and zipfile.is_zipfile(zpath)
    dest_dir = tmp_roots / "out"
    dest_dir.mkdir()
    unzipped = _result({"op": "unzip", "path": str(zpath), "dest": str(dest_dir), "confirm": True})
    assert unzipped["ok"]
    db = tmp_roots / "t.db"
    conn = sqlite3.connect(db)
    conn.execute("create table t(x text)")
    conn.execute("insert into t values ('ok')")
    conn.commit()
    conn.close()
    q = _result({"op": "sqlite", "path": str(db), "sql": "select x from t"})
    assert q["ok"] and q["rows"][0][0] == "ok"
    denied_sql = _result({"op": "sqlite", "path": str(db), "sql": "delete from t"})
    assert denied_sql["ok"] is False
    b64 = _result({"op": "b64", "path": str(src)})
    assert b64["ok"] and b64.get("b64")
    pdf = tmp_roots / "a.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    info = _result({"op": "pdf_info", "path": str(pdf)})
    assert info["ok"] and info.get("pdf") is True


def test_sys_plus_local_and_hooks(monkeypatch):
    import exo_control.sys_plus_ops as y
    which = _result({"op": "which", "name": "python3"})
    assert which["ok"] and which.get("path")
    now = _result({"op": "now"})
    assert now["ok"] and now.get("iso")
    uid = _result({"op": "uuid_gen"})
    assert uid["ok"] and len(uid["uuid"]) >= 32
    ip = _result({"op": "ip_addr"})
    assert ip["ok"]
    dns = _result({"op": "dns", "host": "localhost"})
    assert dns["ok"] and dns.get("addresses") is not None

    def impl(op, step):
        return {"ok": True, "op": op, "hooked": True}

    monkeypatch.setattr(y, "_IMPL", impl)
    assert _result({"op": "ports"})["hooked"]
    assert _result({"op": "uptime"})["hooked"]
    assert _result({"op": "lock_pc"})["ok"] is False
    assert _result({"op": "lock_pc", "confirm": True})["ok"]
    assert _result({"op": "brightness"})["hooked"]
    assert _result({"op": "dark_mode"})["hooked"]


def test_unzip_and_sqlite_write_need_confirm(tmp_roots):
    zpath = tmp_roots / "p.zip"
    with zipfile.ZipFile(zpath, "w") as zf:
        zf.writestr("a.txt", "x")
    assert _result({"op": "unzip", "path": str(zpath), "dest": str(tmp_roots / "u")})["ok"] is False
    db = tmp_roots / "w.db"
    sqlite3.connect(db).close()
    assert _result({"op": "sqlite", "path": str(db), "sql": "create table z(a int)"})["ok"] is False


class FakeBrowser:
    def back(self, space_id=None):
        return {"ok": True, "url": "https://example.com/1"}

    def forward(self, space_id=None):
        return {"ok": True, "url": "https://example.com/2"}

    def reload(self, space_id=None):
        return {"ok": True, "reloaded": True}

    def select(self, selector, value, space_id=None):
        return {"ok": True, "selector": selector, "value": value}

    def upload(self, selector, path, space_id=None):
        return {"ok": True, "path": path}

    def page_dialog(self, action="accept", text=None, space_id=None):
        return {"ok": True, "action": action}

    def storage(self, kind="local", space_id=None):
        return {"ok": True, "kind": kind, "items": {"k": "v"}}

    def cookies(self, space_id=None, include_values=False):
        row = {"name": "sid", "domain": "example.com", "httpOnly": True}
        if include_values:
            row["value"] = "secret"
        return {"ok": True, "cookies": [row]}

    def console_log(self, space_id=None, max_items=40):
        return {"ok": True, "messages": [{"type": "log", "text": "hi"}]}

    def viewport(self, width=None, height=None, space_id=None):
        return {"ok": True, "width": width, "height": height}


def test_browser_wave3_needs_lease(tmp_roots):
    out = _result({"op": "browser_back"})
    assert out["ok"] is False
    assert "lease" in out.get("error", "").lower()


def test_browser_wave3_via_fake(tmp_roots):
    from exo_control.exec_engine import ExoExecEngine

    class Stub:
        def status(self):
            return {"ok": True}

    eng = ExoExecEngine(controller=Stub())
    eng._browser = FakeBrowser()
    src = tmp_roots / "up.txt"
    src.write_text("x", encoding="utf-8")
    out = eng.execute([
        {"op": "lease_acquire", "agent_id": "t", "task": "br", "ttl_sec": 30},
        {"op": "browser_back"},
        {"op": "browser_forward"},
        {"op": "browser_reload"},
        {"op": "browser_select", "selector": "select#x", "value": "a"},
        {"op": "browser_upload", "selector": "input[type=file]", "path": str(src)},
        {"op": "browser_dialog", "action": "accept"},
        {"op": "browser_storage"},
        {"op": "browser_cookies"},
        {"op": "browser_console"},
        {"op": "browser_viewport", "width": 800, "height": 600},
        {"op": "lease_release"},
    ])
    assert out["ok"] is True, out.get("last_error")
    assert out["steps"][1]["result"]["url"].endswith("/1")
    assert out["steps"][8]["result"]["cookies"][0].get("value") is None
    assert out["steps"][10]["result"]["width"] == 800
