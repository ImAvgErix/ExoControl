"""Perplexity Search as Code — mocked HTTP, catalog, lease-free dispatch."""
from __future__ import annotations

import pytest

from aether.exec_engine import ExoExecEngine
from aether.ops_catalog import known_ops, lease_free_ops, lease_required_ops, list_ops
from aether import search_ops


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("EXO_LOCK_DIR", str(tmp_path / "locks"))
    monkeypatch.setenv("EXO_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("EXO_FILE_ROOTS", str(tmp_path / "workspace"))
    monkeypatch.setenv("EXO_LIVE_EYES", "0")
    (tmp_path / "workspace").mkdir()
    yield tmp_path


@pytest.fixture
def key(monkeypatch):
    monkeypatch.setenv("PERPLEXITY_API_KEY", "pplx-test-key")
    yield "pplx-test-key"


def _hits(*rows):
    results = []
    for title, url, snippet in rows:
        results.append({"title": title, "url": url, "snippet": snippet, "date": "2026-08-01"})
    return {"id": "search-1", "results": results}


def test_catalog_has_search_ops():
    names = known_ops()
    for op in ("search", "search_web", "pplx_search", "web_search", "search_content", "search_snippets"):
        assert op in names
    free = lease_free_ops()
    req = lease_required_ops()
    assert "search" in free
    assert "search_content" in free
    assert "search" not in req
    assert "search_content" not in req
    assert not (free & req)
    rows = list_ops(query="search", detail=True)["ops"]
    assert any(r["op"] == "search" for r in rows)
    purpose = next(r["purpose"] for r in rows if r["op"] == "search")
    assert "UI find" in purpose or "not UI" in purpose.lower()


def test_search_fails_closed_without_key(monkeypatch):
    monkeypatch.delenv("PERPLEXITY_API_KEY", raising=False)
    monkeypatch.delenv("EXO_PERPLEXITY_API_KEY", raising=False)
    out = search_ops.search_web({"query": "rust"})
    assert out["ok"] is False
    assert out["code"] == "AUTHENTICATION"
    assert "PERPLEXITY_API_KEY" in out["error"]


def test_search_requires_query(key):
    out = search_ops.search_web({})
    assert out["ok"] is False
    assert out["code"] == "MISSING_QUERY"


def test_search_fanout_dedupe_filter(key, monkeypatch):
    calls = []

    def fake_post(url, headers, payload, timeout):
        calls.append(payload)
        assert headers["Authorization"] == "Bearer pplx-test-key"
        assert url == search_ops.SEARCH_URL
        return 200, _hits(
            ("Tokio", "https://tokio.rs/", "async runtime"),
            ("Tokio docs", "https://tokio.rs", "same host trailing slash"),
            ("Async-std", "https://docs.rs/async-std", "another runtime"),
            ("Unrelated", "https://example.com/x", "cats"),
        ), ""

    monkeypatch.setattr(search_ops, "_POST_JSON", fake_post)
    out = search_ops.search_web({
        "query": ["rust tokio", "rust async-std"],
        "max": 8,
        "contains": "runtime",
        "dedupe": True,
    })
    assert out["ok"] is True
    assert out["provider"] == "perplexity"
    assert out["queries"] == ["rust tokio", "rust async-std"]
    assert calls[0]["query"] == ["rust tokio", "rust async-std"]
    urls = [h["url"] for h in out["results"]]
    assert urls.count("https://tokio.rs/") + urls.count("https://tokio.rs") == 1
    assert all("runtime" in (h["snippet"] + h["title"]).lower() or "runtime" in h["url"] for h in out["results"])
    assert all("cats" not in h["snippet"] for h in out["results"])
    assert out["count"] == len(out["results"])
    assert out["dropped"] >= 1


def test_search_batches_more_than_five_queries(key, monkeypatch):
    calls = []

    def fake_post(url, headers, payload, timeout):
        calls.append(payload["query"])
        q = payload["query"]
        first = q[0] if isinstance(q, list) else q
        return 200, _hits((first, f"https://ex.ample/{len(calls)}", "ok")), ""

    monkeypatch.setattr(search_ops, "_POST_JSON", fake_post)
    queries = [f"q{i}" for i in range(6)]
    out = search_ops.search_web({"query": queries, "max": 2})
    assert out["ok"] is True
    assert out["batches"] == 2
    assert calls[0] == queries[:5]
    assert calls[1] == "q5"


def test_search_http_error_maps_code(key, monkeypatch):
    def fake_post(url, headers, payload, timeout):
        return 429, {"error": {"code": "RATE_LIMIT", "message": "slow down"}}, ""

    monkeypatch.setattr(search_ops, "_POST_JSON", fake_post)
    out = search_ops.search_web({"query": "x"})
    assert out["ok"] is False
    assert out["code"] == "RATE_LIMIT"
    assert out["http_status"] == 429


def test_search_content_scopes_urls(key, monkeypatch):
    def fake_post(url, headers, payload, timeout):
        assert "docs.rs" in payload.get("search_domain_filter", [])
        return 200, _hits(
            ("Tokio", "https://docs.rs/tokio/latest/tokio/", "install with cargo"),
            ("Other", "https://news.ycombinator.com/item?id=1", "install rumor"),
        ), ""

    monkeypatch.setattr(search_ops, "_POST_JSON", fake_post)
    out = search_ops.search_content({
        "query": "installation",
        "urls": ["https://docs.rs/tokio/latest/tokio/"],
    })
    assert out["ok"] is True
    assert out["urls"]
    assert all("docs.rs" in h["url"] for h in out["results"])


def test_search_content_requires_urls(key):
    out = search_ops.search_content({"query": "x"})
    assert out["ok"] is False
    assert out["code"] == "MISSING_URLS"


def test_search_via_exec_is_lease_free(home, key, monkeypatch):
    def fake_post(url, headers, payload, timeout):
        return 200, _hits(("A", "https://a.example/1", "hello from search")), ""

    monkeypatch.setattr(search_ops, "_POST_JSON", fake_post)
    eng = ExoExecEngine()
    out = eng.execute([{"op": "search", "query": "hello", "max": 3}])
    assert out["ok"] is True, out.get("last_error") or out
    step = out["steps"][0]
    assert step["ok"] is True
    assert step["op"] == "search"
    body = step["result"]
    assert body["ok"] is True
    assert body["results"]
    assert body["results"][0]["title"] == "A"


def test_search_alias_web_search(home, key, monkeypatch):
    monkeypatch.setattr(
        search_ops,
        "_POST_JSON",
        lambda *a, **k: (200, _hits(("B", "https://b.example/", "x")), ""),
    )
    eng = ExoExecEngine()
    out = eng.execute([{"op": "web_search", "q": "alias"}])
    assert out["ok"] is True
    assert out["steps"][0]["result"]["results"][0]["title"] == "B"


def test_status_reports_search_capability(home, key):
    eng = ExoExecEngine()
    out = eng.execute([{"op": "status"}])
    caps = out["steps"][0]["result"]["capabilities"]
    assert caps["search_web"] is True
    assert caps["search_configured"] is True


def test_status_search_configured_false(home, monkeypatch):
    monkeypatch.delenv("PERPLEXITY_API_KEY", raising=False)
    monkeypatch.delenv("EXO_PERPLEXITY_API_KEY", raising=False)
    eng = ExoExecEngine()
    out = eng.execute([{"op": "status"}])
    assert out["steps"][0]["result"]["capabilities"]["search_configured"] is False


def test_exo_key_alias(monkeypatch):
    monkeypatch.delenv("PERPLEXITY_API_KEY", raising=False)
    monkeypatch.setenv("EXO_PERPLEXITY_API_KEY", "exo-key")
    assert search_ops.configured() is True
    assert search_ops.api_key() == "exo-key"


def test_aether_search_ops_shim():
    import aether.search_ops as shim
    import exo_control.search_ops as impl
    assert shim.search_web is impl.search_web


def test_rank_recency(key, monkeypatch):
    def fake_post(url, headers, payload, timeout):
        return 200, {
            "id": "r",
            "results": [
                {"title": "old", "url": "https://a.example/old", "snippet": "a", "date": "2020-01-01"},
                {"title": "new", "url": "https://a.example/new", "snippet": "b", "last_updated": "2026-08-14"},
            ],
        }, ""

    monkeypatch.setattr(search_ops, "_POST_JSON", fake_post)
    out = search_ops.search_web({"query": "x", "rank": "recency"})
    assert [h["title"] for h in out["results"]] == ["new", "old"]
