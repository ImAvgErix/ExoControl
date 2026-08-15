"""Wave 2 desk ops: Docling, RAG, search APIs, SaaS, shells, Windows sys."""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

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
    "docling", "rag", "winsearch", "steel_start",
    "tavily", "exa", "slack", "notion", "linear",
    "pwsh", "wsl", "docker",
    "print", "wifi", "power", "disk", "whoami", "certs", "hash", "lnk", "dialog",
]

CAP_KEYS = [
    "docling", "rag", "winsearch", "steel", "tavily", "exa",
    "slack", "notion", "linear", "pwsh", "wsl", "docker",
    "print", "wifi", "power", "disk", "whoami", "certs", "hash", "lnk", "dialog",
]


def test_wave2_catalog_lease_free():
    from exo_control.ops_catalog import get_op
    for name in LEASE_FREE:
        spec = get_op(name)
        assert spec is not None, name
        assert spec.get("lease") is False, name


def test_wave2_capabilities_keys():
    from exo_control.addon_ops import capabilities
    caps = capabilities()
    for key in CAP_KEYS:
        assert key in caps, key


def test_wave2_aether_shims():
    import aether.docling_ops as d
    import aether.rag_ops as r
    import aether.steel_ops as s
    import aether.web_search_ops as w
    import aether.saas_ops as sa
    import aether.shell_ops as sh
    import aether.win_sys_ops as ws
    assert d.__name__ == "exo_control.docling_ops"
    assert r.__name__ == "exo_control.rag_ops"
    assert s.__name__ == "exo_control.steel_ops"
    assert w.__name__ == "exo_control.web_search_ops"
    assert sa.__name__ == "exo_control.saas_ops"
    assert sh.__name__ == "exo_control.shell_ops"
    assert ws.__name__ == "exo_control.win_sys_ops"


def test_docling_txt_and_hook(tmp_roots, monkeypatch):
    note = tmp_roots / "note.txt"
    note.write_text("hello docling", encoding="utf-8")
    out = _result({"op": "docling", "path": str(note)})
    assert out["ok"] is True
    assert "hello docling" in out["markdown"]

    pdf = tmp_roots / "a.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    import exo_control.docling_ops as d
    monkeypatch.setattr(d, "_CONVERT", lambda path: "# From Docling")
    hooked = _result({"op": "docling", "path": str(pdf)})
    assert hooked["ok"] is True
    assert hooked["markdown"] == "# From Docling"


def test_rag_local_snippets(tmp_roots):
    (tmp_roots / "notes.md").write_text("The Q3 forecast is green.\nOther line.\n", encoding="utf-8")
    (tmp_roots / "other.txt").write_text("unrelated apples\n", encoding="utf-8")
    out = _result({"op": "rag", "query": "forecast"})
    assert out["ok"] is True
    assert out["hits"]
    assert any("forecast" in (h.get("text") or "").lower() for h in out["hits"])


def test_tavily_and_exa(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "tv-test")
    monkeypatch.setenv("EXA_API_KEY", "exa-test")
    import exo_control.web_search_ops as w

    def fake(method, url, headers, payload, timeout):
        if "tavily" in url:
            return 200, {"results": [{"title": "T", "url": "https://t.example", "content": "hi"}]}, ""
        return 200, {"results": [{"title": "E", "url": "https://e.example"}]}, ""

    monkeypatch.setattr(w, "_REQUEST_JSON", fake)
    tv = _result({"op": "tavily", "query": "rust async"})
    ex = _result({"op": "exa", "query": "rust async"})
    assert tv["ok"] and tv["results"][0]["title"] == "T"
    assert ex["ok"] and ex["results"][0]["title"] == "E"


def test_tavily_fails_closed_without_key(monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    monkeypatch.delenv("EXO_TAVILY_API_KEY", raising=False)
    out = _result({"op": "tavily", "query": "x"})
    assert out["ok"] is False
    assert out.get("code") == "AUTHENTICATION"


def test_steel_start_and_stop(monkeypatch):
    monkeypatch.setenv("STEEL_API_KEY", "steel-test")
    import exo_control.steel_ops as s

    def fake(method, url, headers, payload, timeout):
        if method == "POST":
            return 201, {"id": "ses-1", "websocketUrl": "wss://connect.steel.dev/cdp/1"}, ""
        return 200, {"ok": True}, ""

    monkeypatch.setattr(s, "_REQUEST_JSON", fake)
    started = _result({"op": "steel_start"})
    assert started["ok"] is True
    assert started["id"] == "ses-1"
    assert "wss://" in (started.get("cdp_url") or "")
    stopped = _result({"op": "steel_stop", "id": "ses-1"})
    assert stopped["ok"] is True


def test_slack_notion_linear(monkeypatch):
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-test")
    monkeypatch.setenv("NOTION_API_KEY", "ntn-test")
    monkeypatch.setenv("LINEAR_API_KEY", "lin_test")
    import exo_control.saas_ops as sa

    def fake(method, url, headers, payload, timeout):
        if "slack" in url:
            return 200, {"ok": True, "channels": [{"id": "C1", "name": "eng"}]}, ""
        if "notion" in url:
            return 200, {"results": [{"id": "p1", "object": "page"}]}, ""
        return 200, {"data": {"issues": {"nodes": [{"id": "i1", "title": "Bug", "identifier": "ENG-1"}]}}}, ""

    monkeypatch.setattr(sa, "_REQUEST_JSON", fake)
    slack = _result({"op": "slack", "action": "list"})
    notion = _result({"op": "notion", "query": "roadmap"})
    linear = _result({"op": "linear", "query": "bug"})
    assert slack["ok"] and slack["channels"][0]["name"] == "eng"
    assert notion["ok"] and notion["pages"][0]["id"] == "p1"
    assert linear["ok"] and linear["issues"][0]["identifier"] == "ENG-1"


def test_slack_post_requires_confirm(monkeypatch):
    monkeypatch.setenv("SLACK_TOKEN", "xoxb-test")
    import exo_control.saas_ops as sa
    monkeypatch.setattr(sa, "_REQUEST_JSON", lambda *a, **k: (200, {"ok": True, "ts": "1"}, ""))
    denied = _result({"op": "slack", "channel": "C1", "text": "hi"})
    assert denied["ok"] is False
    assert "confirm" in denied.get("error", "").lower()
    ok = _result({"op": "slack", "channel": "C1", "text": "hi", "confirm": True})
    assert ok["ok"] is True


def test_pwsh_requires_confirm(monkeypatch):
    import exo_control.shell_ops as sh
    monkeypatch.setattr(sh, "_RUN", lambda op, step: {"ok": True, "stdout": "ok"})
    denied = _result({"op": "pwsh", "script": "Get-Date"})
    assert denied["ok"] is False
    assert "confirm" in denied.get("error", "").lower()
    ok = _result({"op": "pwsh", "script": "Get-Date", "confirm": True})
    assert ok["ok"] is True


def test_wsl_list_and_docker_ps(monkeypatch):
    import exo_control.shell_ops as sh

    def run(op, step):
        if op == "wsl":
            return {"ok": True, "distros": ["Ubuntu"]}
        if op == "docker":
            return {"ok": True, "containers": [{"id": "c1", "image": "nginx"}]}
        return None

    monkeypatch.setattr(sh, "_RUN", run)
    assert _result({"op": "wsl", "action": "list"})["distros"] == ["Ubuntu"]
    assert _result({"op": "docker", "action": "ps"})["containers"][0]["image"] == "nginx"


def test_docker_run_requires_confirm(monkeypatch):
    import exo_control.shell_ops as sh
    monkeypatch.setattr(sh, "_RUN", lambda op, step: {"ok": True, "id": "c2"})
    denied = _result({"op": "docker", "action": "run", "image": "alpine"})
    assert denied["ok"] is False
    ok = _result({"op": "docker", "action": "run", "image": "alpine", "confirm": True})
    assert ok["ok"] is True


def test_hash_and_whoami_and_disk(tmp_roots):
    f = tmp_roots / "a.bin"
    f.write_bytes(b"abc")
    digest = hashlib.sha256(b"abc").hexdigest()
    hashed = _result({"op": "hash", "path": str(f)})
    assert hashed["ok"] is True
    assert hashed["sha256"] == digest
    me = _result({"op": "whoami"})
    assert me["ok"] is True
    assert me.get("user")
    disk = _result({"op": "disk", "path": str(tmp_roots)})
    assert disk["ok"] is True
    assert disk.get("free") is not None


def test_win_sys_hooks(monkeypatch):
    import exo_control.win_sys_ops as w

    def impl(op, step):
        if op == "winsearch":
            return {"ok": True, "hits": [{"name": "a.txt"}]}
        if op == "print":
            return {"ok": True, "printed": True}
        if op == "wifi":
            return {"ok": True, "networks": [{"ssid": "Home"}]}
        if op == "power":
            return {"ok": True, "plugged": True, "percent": 80}
        if op == "certs":
            return {"ok": True, "certs": [{"subject": "CN=Test"}]}
        if op == "lnk":
            return {"ok": True, "target": "C:/Windows/notepad.exe"}
        if op == "dialog":
            return {"ok": True, "shown": True}
        return None

    monkeypatch.setattr(w, "_IMPL", impl)
    assert _result({"op": "winsearch", "query": "a.txt"})["hits"][0]["name"] == "a.txt"
    assert _result({"op": "wifi"})["networks"][0]["ssid"] == "Home"
    assert _result({"op": "power"})["percent"] == 80
    assert _result({"op": "certs"})["certs"][0]["subject"] == "CN=Test"
    assert _result({"op": "lnk", "path": "x.lnk"})["target"].endswith("notepad.exe")


def test_print_dialog_power_sleep_need_confirm(monkeypatch):
    import exo_control.win_sys_ops as w
    monkeypatch.setattr(w, "_IMPL", lambda op, step: {"ok": True, "done": True})
    assert _result({"op": "print", "path": "a.pdf"})["ok"] is False
    assert _result({"op": "print", "path": "a.pdf", "confirm": True})["ok"] is True
    assert _result({"op": "dialog", "text": "hi"})["ok"] is False
    assert _result({"op": "dialog", "text": "hi", "confirm": True})["ok"] is True
    assert _result({"op": "power", "action": "sleep"})["ok"] is False
    assert _result({"op": "power", "action": "sleep", "confirm": True})["ok"] is True


def test_lnk_create_requires_confirm(monkeypatch):
    import exo_control.win_sys_ops as w
    monkeypatch.setattr(w, "_IMPL", lambda op, step: {"ok": True, "created": True})
    denied = _result({"op": "lnk", "path": "x.lnk", "target": "C:/Windows/notepad.exe"})
    assert denied["ok"] is False
    ok = _result({"op": "lnk", "path": "x.lnk", "target": "C:/Windows/notepad.exe", "confirm": True})
    assert ok["ok"] is True


def test_winsearch_unavailable_on_linux_without_hook(monkeypatch):
    if sys.platform == "win32":
        pytest.skip("Windows has native impl")
    import exo_control.win_sys_ops as w
    monkeypatch.setattr(w, "_IMPL", None)
    out = _result({"op": "winsearch", "query": "x"})
    assert out["ok"] is False
    assert out.get("code") in {"WINDOWS_ONLY", "UNAVAILABLE"}
