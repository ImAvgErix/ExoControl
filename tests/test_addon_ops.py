"""Lease-free addon ops: Firecrawl, MarkItDown, Stagehand, Skyvern, OmniParser,
AgentQL, Everything, Mem0, Composio/Graph, Screenpipe.
"""
from __future__ import annotations

import json

import pytest

from aether.exec_engine import ExoExecEngine
from aether.ops_catalog import known_ops, lease_free_ops, lease_required_ops


ADDON_OPS = (
    "scrape", "crawl", "site_map",
    "files_convert", "read_doc",
    "stagehand", "browser_act", "stagehand_extract", "browser_extract",
    "skyvern",
    "omni", "omni_parse",
    "agentql", "browser_query",
    "files_find",
    "memory_add", "memory_search",
    "composio", "mail_list", "cal_next", "drive_get",
    "recall", "screen_search",
)


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("EXO_LOCK_DIR", str(tmp_path / "locks"))
    monkeypatch.setenv("EXO_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("EXO_FILE_ROOTS", str(tmp_path / "workspace"))
    monkeypatch.setenv("EXO_LIVE_EYES", "0")
    (tmp_path / "workspace").mkdir()
    (tmp_path / "state").mkdir()
    yield tmp_path


def test_catalog_lists_all_addons_as_lease_free():
    names = known_ops()
    free = lease_free_ops()
    req = lease_required_ops()
    for op in ADDON_OPS:
        assert op in names, op
        assert op in free, op
        assert op not in req, op
    assert not (free & req)


def test_browser_act_alias_is_lease_free_not_hands():
    """browser_* usually needs a lease; Stagehand/AgentQL HTTP aliases must not."""
    assert "browser_act" in lease_free_ops()
    assert "browser_extract" in lease_free_ops()
    assert "browser_query" in lease_free_ops()
    assert "browser_connect" in lease_required_ops()


def test_firecrawl_fails_closed_without_key(monkeypatch):
    from aether import firecrawl_ops

    monkeypatch.delenv("FIRECRAWL_API_KEY", raising=False)
    monkeypatch.delenv("EXO_FIRECRAWL_API_KEY", raising=False)
    out = firecrawl_ops.scrape({"url": "https://example.com"})
    assert out["ok"] is False
    assert out["code"] == "AUTHENTICATION"
    assert "FIRECRAWL_API_KEY" in out["error"]


def test_firecrawl_scrape_map_crawl(monkeypatch):
    from aether import firecrawl_ops

    monkeypatch.setenv("FIRECRAWL_API_KEY", "fc-test")
    calls = []

    def fake(method, url, headers, payload, timeout):
        calls.append((method, url, payload))
        assert headers["Authorization"] == "Bearer fc-test"
        if url.endswith("/scrape"):
            return 200, {
                "success": True,
                "data": {"markdown": "# Hello", "metadata": {"title": "Example"}},
            }, ""
        if url.endswith("/map"):
            return 200, {"success": True, "links": ["https://example.com/", "https://example.com/a"]}, ""
        if url.endswith("/crawl"):
            return 200, {"success": True, "id": "job-1"}, ""
        return 404, {}, ""

    monkeypatch.setattr(firecrawl_ops, "_REQUEST_JSON", fake)
    scraped = firecrawl_ops.scrape({"url": "https://example.com"})
    assert scraped["ok"] is True
    assert scraped["provider"] == "firecrawl"
    assert scraped["markdown"].startswith("# Hello")
    assert scraped["title"] == "Example"

    mapped = firecrawl_ops.site_map({"url": "https://example.com"})
    assert mapped["ok"] is True
    assert mapped["count"] == 2

    crawled = firecrawl_ops.crawl({"url": "https://example.com", "limit": 3})
    assert crawled["ok"] is True
    assert crawled["id"] == "job-1"
    assert any(c[1].endswith("/scrape") for c in calls)


def test_scrape_via_exec_is_lease_free(home, monkeypatch):
    from aether import firecrawl_ops

    monkeypatch.setenv("FIRECRAWL_API_KEY", "fc-test")
    monkeypatch.setattr(
        firecrawl_ops,
        "_REQUEST_JSON",
        lambda *a, **k: (200, {"success": True, "data": {"markdown": "x", "metadata": {}}}, ""),
    )
    eng = ExoExecEngine()
    out = eng.execute([{"op": "scrape", "url": "https://example.com"}])
    assert out["ok"] is True, out.get("last_error") or out
    assert out["steps"][0]["result"]["ok"] is True


def test_files_convert_txt_and_allowroot(home):
    from aether import markitdown_ops

    root = home / "workspace"
    (root / "note.txt").write_text("hello doc", encoding="utf-8")
    out = markitdown_ops.convert({"path": str(root / "note.txt")})
    assert out["ok"] is True
    assert out["provider"] == "markitdown"
    assert "hello doc" in out["markdown"]

    secret = home / "secret.pdf"
    secret.write_bytes(b"%PDF")
    denied = markitdown_ops.convert({"path": str(secret)})
    assert denied["ok"] is False
    assert "allowroot" in denied["error"] or "EXO_FILE_ROOTS" in denied["error"]


def test_files_convert_pdf_uses_hook(home, monkeypatch):
    from aether import markitdown_ops

    pdf = home / "workspace" / "a.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    monkeypatch.setattr(markitdown_ops, "_CONVERT", lambda path: "# From PDF")
    out = markitdown_ops.convert({"path": str(pdf)})
    assert out["ok"] is True
    assert out["markdown"] == "# From PDF"


def test_stagehand_and_skyvern_and_agentql_auth(monkeypatch):
    from aether import agentql_ops, skyvern_ops, stagehand_ops

    for name in (
        "BROWSERBASE_API_KEY", "STAGEHAND_API_KEY", "EXO_STAGEHAND_API_KEY",
        "SKYVERN_API_KEY", "EXO_SKYVERN_API_KEY",
        "AGENTQL_API_KEY", "EXO_AGENTQL_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)
    assert stagehand_ops.act({"instruction": "click checkout"})["code"] == "AUTHENTICATION"
    assert skyvern_ops.run_task({"task": "fill the form"})["code"] == "AUTHENTICATION"
    assert agentql_ops.query({"url": "https://x.test", "query": "{ title }"})["code"] == "AUTHENTICATION"


def test_stagehand_act_extract(monkeypatch):
    from aether import stagehand_ops

    monkeypatch.setenv("BROWSERBASE_API_KEY", "bb-key")
    monkeypatch.setenv("MODEL_API_KEY", "model-key")

    def fake(method, url, headers, payload, timeout):
        assert headers["Authorization"] == "Bearer bb-key"
        assert "act" in url or "extract" in url
        if "extract" in url:
            return 200, {"ok": True, "data": {"price": "9"}}, ""
        return 200, {"ok": True, "action": "clicked"}, ""

    monkeypatch.setattr(stagehand_ops, "_REQUEST_JSON", fake)
    acted = stagehand_ops.act({"instruction": "click checkout", "url": "https://shop.test"})
    assert acted["ok"] is True
    assert acted["provider"] == "stagehand"
    extracted = stagehand_ops.extract({"instruction": "price", "url": "https://shop.test"})
    assert extracted["ok"] is True
    assert extracted["data"]["price"] == "9"


def test_browser_act_via_exec_is_lease_free(home, monkeypatch):
    from aether import stagehand_ops

    monkeypatch.setenv("STAGEHAND_API_KEY", "sh-key")
    monkeypatch.setattr(
        stagehand_ops,
        "_REQUEST_JSON",
        lambda *a, **k: (200, {"ok": True, "action": "done"}, ""),
    )
    eng = ExoExecEngine()
    out = eng.execute([{"op": "browser_act", "instruction": "open cart"}])
    assert out["ok"] is True, out.get("last_error") or out
    assert out["steps"][0]["result"]["ok"] is True


def test_skyvern_creates_task(monkeypatch):
    from aether import skyvern_ops

    monkeypatch.setenv("SKYVERN_API_KEY", "sk-test")

    def fake(method, url, headers, payload, timeout):
        assert headers["x-api-key"] == "sk-test"
        assert url.endswith("/v1/run/tasks")
        assert payload["prompt"] == "Get the title"
        return 200, {"run_id": "run-1", "status": "created"}, ""

    monkeypatch.setattr(skyvern_ops, "_REQUEST_JSON", fake)
    out = skyvern_ops.run_task({"task": "Get the title", "url": "https://news.ycombinator.com"})
    assert out["ok"] is True
    assert out["run_id"] == "run-1"
    assert out["provider"] == "skyvern"


def test_omni_fails_closed_without_backend(monkeypatch):
    from aether import omniparser_ops

    monkeypatch.delenv("OMNIPARSER_URL", raising=False)
    monkeypatch.delenv("EXO_OMNIPARSER_URL", raising=False)
    monkeypatch.setattr(omniparser_ops, "_PARSE", None)
    out = omniparser_ops.parse({"path": "shot.png"})
    assert out["ok"] is False
    assert out["code"] in {"UNAVAILABLE", "NOT_INSTALLED"}


def test_omni_parse_hook(home, monkeypatch):
    from aether import omniparser_ops

    shot = home / "workspace" / "ui.png"
    shot.write_bytes(b"\x89PNG")
    monkeypatch.setattr(
        omniparser_ops,
        "_PARSE",
        lambda step, path: [{"label": "OK", "x": 10, "y": 20}],
    )
    out = omniparser_ops.parse({"path": str(shot)})
    assert out["ok"] is True
    assert out["provider"] == "omniparser"
    assert out["elements"][0]["label"] == "OK"


def test_agentql_query(monkeypatch):
    from aether import agentql_ops

    monkeypatch.setenv("AGENTQL_API_KEY", "aq-key")

    def fake(method, url, headers, payload, timeout):
        assert headers.get("X-API-Key") == "aq-key" or headers.get("x-api-key") == "aq-key"
        assert payload["url"] == "https://shop.test"
        return 200, {"data": {"title": "Widget", "price": "9"}}, ""

    monkeypatch.setattr(agentql_ops, "_REQUEST_JSON", fake)
    out = agentql_ops.query({"url": "https://shop.test", "query": "{ title, price }"})
    assert out["ok"] is True
    assert out["data"]["title"] == "Widget"


def test_files_find_walk_fallback(home, monkeypatch):
    from aether import everything_ops

    root = home / "workspace"
    (root / "Q3-forecast.xlsx").write_bytes(b"x")
    (root / "other.txt").write_text("no", encoding="utf-8")
    monkeypatch.setattr(
        everything_ops,
        "_REQUEST_JSON",
        lambda *a, **k: (0, {"error": {"code": "CONNECT", "message": "down"}}, ""),
    )
    out = everything_ops.find({"query": "forecast"})
    assert out["ok"] is True
    assert out["fallback"] == "walk"
    names = [r["name"] for r in out["results"]]
    assert "Q3-forecast.xlsx" in names
    assert "other.txt" not in names


def test_files_find_everything_http_filters_roots(home, monkeypatch):
    from aether import everything_ops

    root = home / "workspace"
    inside = root / "keep.txt"
    outside = home / "secret.txt"
    inside.write_text("in", encoding="utf-8")
    outside.write_text("out", encoding="utf-8")

    def fake(method, url, headers, payload, timeout):
        return 200, {
            "totalResults": 2,
            "results": [
                {"name": "keep.txt", "path": str(root)},
                {"name": "secret.txt", "path": str(home)},
            ],
        }, ""

    monkeypatch.setattr(everything_ops, "_REQUEST_JSON", fake)
    out = everything_ops.find({"query": "txt"})
    assert out["ok"] is True
    assert out["provider"] == "everything"
    paths = [r["path"] for r in out["results"]]
    assert any("keep.txt" in p for p in paths)
    assert not any("secret.txt" in p for p in paths)


def test_memory_local_add_and_search(home):
    from aether import memory_ops

    added = memory_ops.add({"text": "User prefers dark mode", "user_id": "desk"})
    assert added["ok"] is True
    assert added["provider"] in {"local", "mem0"}
    found = memory_ops.search({"query": "dark", "user_id": "desk"})
    assert found["ok"] is True
    assert found["count"] >= 1
    assert any("dark" in str(m.get("text") or "").lower() for m in found["memories"])


def test_memory_mem0_http(home, monkeypatch):
    from aether import memory_ops

    monkeypatch.setenv("MEM0_API_KEY", "m0-key")
    calls = []

    def fake(method, url, headers, payload, timeout):
        calls.append((method, url, payload))
        if method == "POST" and url.rstrip("/").endswith("search"):
            return 200, {"results": [{"memory": "nuts allergy", "id": "1"}]}, ""
        return 200, {"id": "mem-1"}, ""

    monkeypatch.setattr(memory_ops, "_REQUEST_JSON", fake)
    added = memory_ops.add({"text": "allergic to nuts"})
    assert added["ok"] is True
    assert added["provider"] == "mem0"
    found = memory_ops.search({"query": "allergy"})
    assert found["ok"] is True
    assert found["memories"]


def test_composio_and_graph_auth(monkeypatch):
    from aether import composio_ops

    for name in (
        "COMPOSIO_API_KEY", "EXO_COMPOSIO_API_KEY",
        "MICROSOFT_GRAPH_TOKEN", "EXO_GRAPH_TOKEN", "AZURE_TOKEN",
    ):
        monkeypatch.delenv(name, raising=False)
    assert composio_ops.mail_list({})["code"] == "AUTHENTICATION"
    assert composio_ops.run({"action": "GMAIL_SEND_EMAIL"})["code"] == "AUTHENTICATION"


def test_mail_list_graph(monkeypatch):
    from aether import composio_ops

    monkeypatch.setenv("MICROSOFT_GRAPH_TOKEN", "tok")

    def fake(method, url, headers, payload, timeout):
        assert headers["Authorization"] == "Bearer tok"
        assert "graph.microsoft.com" in url
        return 200, {
            "value": [
                {"subject": "Hello", "from": {"emailAddress": {"address": "a@b.com"}}, "receivedDateTime": "2026-08-15"},
            ]
        }, ""

    monkeypatch.setattr(composio_ops, "_REQUEST_JSON", fake)
    out = composio_ops.mail_list({"max": 5})
    assert out["ok"] is True
    assert out["provider"] == "microsoft-graph"
    assert out["messages"][0]["subject"] == "Hello"


def test_composio_execute(monkeypatch):
    from aether import composio_ops

    monkeypatch.setenv("COMPOSIO_API_KEY", "ck")

    def fake(method, url, headers, payload, timeout):
        assert "GMAIL_FETCH_EMAILS" in url or (payload or {}).get("action") == "GMAIL_FETCH_EMAILS"
        return 200, {"successful": True, "data": {"messages": []}}, ""

    monkeypatch.setattr(composio_ops, "_REQUEST_JSON", fake)
    out = composio_ops.run({"action": "GMAIL_FETCH_EMAILS"})
    assert out["ok"] is True
    assert out["provider"] == "composio"


def test_composio_send_requires_confirm(monkeypatch):
    from aether import composio_ops

    monkeypatch.setenv("COMPOSIO_API_KEY", "ck")
    out = composio_ops.run({"action": "GMAIL_SEND_EMAIL", "input": {"to": "a@b.com"}})
    assert out["ok"] is False
    assert "confirm" in out["error"]


def test_screenpipe_fails_closed_when_down(monkeypatch):
    from aether import screenpipe_ops

    monkeypatch.setattr(
        screenpipe_ops,
        "_REQUEST_JSON",
        lambda *a, **k: (0, {"error": {"code": "CONNECT", "message": "down"}}, ""),
    )
    out = screenpipe_ops.search({"query": "meeting"})
    assert out["ok"] is False
    assert out["code"] in {"CONNECT", "UNAVAILABLE"}


def test_recall_search(monkeypatch):
    from aether import screenpipe_ops

    def fake(method, url, headers, payload, timeout):
        assert "3030" in url or "search" in url
        return 200, {"data": [{"content": "standup notes", "app_name": "Slack"}]}, ""

    monkeypatch.setattr(screenpipe_ops, "_REQUEST_JSON", fake)
    out = screenpipe_ops.search({"query": "standup"})
    assert out["ok"] is True
    assert out["provider"] == "screenpipe"
    assert out["results"]


def test_status_reports_addon_capabilities(home, monkeypatch):
    monkeypatch.setenv("FIRECRAWL_API_KEY", "fc")
    eng = ExoExecEngine()
    out = eng.execute([{"op": "status"}])
    caps = out["steps"][0]["result"]["capabilities"]
    assert caps["firecrawl"] is True
    assert caps["firecrawl_configured"] is True
    assert caps["markitdown"] is True
    assert caps["stagehand"] is True
    assert caps["skyvern"] is True
    assert caps["omniparser"] is True
    assert caps["agentql"] is True
    assert caps["everything"] is True
    assert caps["memory"] is True
    assert caps["composio"] is True
    assert caps["screenpipe"] is True


def test_aether_shims():
    import aether.firecrawl_ops as fc
    import exo_control.firecrawl_ops as impl
    assert fc.scrape is impl.scrape


def test_help_mentions_addons():
    from aether.ops_catalog import list_ops, mcp_instructions

    rows = list_ops(query="scrape", detail=True)["ops"]
    assert any(r["op"] == "scrape" for r in rows)
    text = mcp_instructions()
    assert "scrape" in text or "Firecrawl" in text or "firecrawl" in text.lower()
