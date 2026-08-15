"""Merged overlapping ops: one catalog entry, aliases + provider/engine still work."""
from __future__ import annotations

import re
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


def _engine_op_names() -> set:
    text = (SRC / "exo_control" / "exec_engine.py").read_text(encoding="utf-8")
    names = set(re.findall(r'op == "([a-z0-9_]+)"', text))
    for block in re.findall(r"op in \{([^}]+)\}", text):
        names.update(re.findall(r'"([a-z0-9_]+)"', block))
    return names


def test_catalog_names_are_unique():
    from exo_control.ops_catalog import OPS, _names

    seen = []
    for entry in OPS:
        seen.extend(_names(entry))
    dups = sorted({n for n in seen if seen.count(n) > 1})
    assert dups == [], dups


def test_every_catalog_name_is_wired():
    from exo_control.addon_ops import ROUTES
    from exo_control.ops_catalog import known_ops

    missing = sorted(known_ops() - set(ROUTES) - _engine_op_names())
    assert missing == [], missing


def test_search_family_is_one_catalog_entry():
    from exo_control.ops_catalog import get_op

    canon = get_op("search")
    assert canon is not None
    assert canon["op"] == "search"
    for name in (
        "search_web", "tavily", "exa", "ddg", "serper", "brave",
        "tavily_search", "exa_search", "duckduckgo", "serper_search", "brave_search",
    ):
        spec = get_op(name)
        assert spec is canon or (spec and spec["op"] == "search"), name
    purpose = (canon.get("purpose") or "").lower()
    assert "not ui" in purpose or "ui find" in purpose
    assert "provider" in purpose or "provider?" in " ".join(canon.get("fields") or [])


def test_convert_and_scrape_families_merged():
    from exo_control.ops_catalog import get_op

    convert = get_op("files_convert")
    assert convert and convert["op"] == "files_convert"
    for name in ("docling", "docling_convert", "markitdown", "read_doc"):
        spec = get_op(name)
        assert spec and spec["op"] == "files_convert", name

    scrape = get_op("scrape")
    assert scrape and scrape["op"] == "scrape"
    for name in ("read_url", "jina", "url_md", "firecrawl"):
        spec = get_op(name)
        assert spec and spec["op"] == "scrape", name

    stat = get_op("files_stat")
    assert stat and stat["op"] == "files_stat"
    for name in ("pdf_info", "image_info", "stat"):
        spec = get_op(name)
        assert spec and spec["op"] == "files_stat", name


def test_search_provider_routes_without_breaking_aliases(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "tv-test")
    monkeypatch.setenv("EXA_API_KEY", "exa-test")
    monkeypatch.setenv("SERPER_API_KEY", "sp-test")
    monkeypatch.setenv("BRAVE_API_KEY", "br-test")
    monkeypatch.setenv("PERPLEXITY_API_KEY", "pplx-test")

    import exo_control.search_ops as pplx
    import exo_control.web_search_ops as w
    import exo_control.open_data_ops as o
    import exo_control.saas2_ops as s2

    def fake_web(method, url, headers, payload, timeout):
        if "tavily" in url:
            return 200, {"results": [{"title": "T", "url": "https://t.example"}]}, ""
        if "exa" in url:
            return 200, {"results": [{"title": "E", "url": "https://e.example"}]}, ""
        if "serper" in url:
            return 200, {"organic": [{"title": "S", "link": "https://s.example"}]}, ""
        if "brave" in url:
            return 200, {"web": {"results": [{"title": "B", "url": "https://b.example"}]}}, ""
        if "duckduckgo" in url:
            return 200, {"AbstractText": "DDG", "RelatedTopics": []}, ""
        return 500, {"error": url}, ""

    monkeypatch.setattr(w, "_REQUEST_JSON", fake_web)
    monkeypatch.setattr(o, "_REQUEST_JSON", fake_web)
    monkeypatch.setattr(s2, "_REQUEST_JSON", fake_web)
    monkeypatch.setattr(
        pplx,
        "_POST_JSON",
        lambda *a, **k: (200, {"results": [{"title": "P", "url": "https://p.example", "snippet": "x"}]}, ""),
    )

    tv = _result({"op": "tavily", "query": "rust"})
    assert tv["ok"] and tv.get("provider") == "tavily"
    via = _result({"op": "search", "provider": "tavily", "query": "rust"})
    assert via["ok"] and via.get("provider") == "tavily"

    ex = _result({"op": "search", "provider": "exa", "query": "rust"})
    assert ex["ok"] and ex.get("provider") == "exa"

    ddg = _result({"op": "ddg", "query": "rust"})
    assert ddg["ok"] and ddg.get("provider") in {"duckduckgo", "ddg"}
    ddg2 = _result({"op": "search", "provider": "ddg", "query": "rust"})
    assert ddg2["ok"]

    sp = _result({"op": "search", "provider": "serper", "query": "rust"})
    assert sp["ok"] and sp.get("provider") == "serper"
    br = _result({"op": "brave", "query": "rust"})
    assert br["ok"] and br.get("provider") == "brave"

    px = _result({"op": "search", "query": "rust"})
    assert px["ok"] and px.get("provider") == "perplexity"

    bad = _result({"op": "search", "provider": "nope", "query": "rust"})
    assert bad["ok"] is False
    assert bad.get("code") == "BAD_PROVIDER"


def test_files_convert_engine_docling(tmp_roots, monkeypatch):
    note = tmp_roots / "note.txt"
    note.write_text("hello convert", encoding="utf-8")
    defaulted = _result({"op": "files_convert", "path": str(note)})
    assert defaulted["ok"] is True
    assert defaulted.get("provider") == "markitdown"

    import exo_control.docling_ops as d
    monkeypatch.setattr(d, "_CONVERT", lambda path: "# From Docling")
    pdf = tmp_roots / "a.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    via_alias = _result({"op": "docling", "path": str(pdf)})
    assert via_alias["ok"] is True
    assert via_alias.get("provider") == "docling"
    via_engine = _result({"op": "files_convert", "engine": "docling", "path": str(pdf)})
    assert via_engine["ok"] is True
    assert via_engine.get("provider") == "docling"
    assert via_engine["markdown"] == "# From Docling"


def test_scrape_provider_jina(monkeypatch):
    import exo_control.jina_ops as j

    def fake(method, url, headers, timeout):
        assert url.startswith("https://r.jina.ai/")
        return 200, "# Jina page", ""

    monkeypatch.setattr(j, "_REQUEST_TEXT", fake)
    alias = _result({"op": "read_url", "url": "https://example.com/doc"})
    assert alias["ok"] is True
    assert alias.get("provider") == "jina"
    via = _result({"op": "scrape", "provider": "jina", "url": "https://example.com/doc"})
    assert via["ok"] is True
    assert via.get("provider") == "jina"
    assert "Jina" in via["markdown"]


def test_files_stat_includes_pdf_and_image_extras(tmp_roots):
    pdf = tmp_roots / "a.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    info = _result({"op": "pdf_info", "path": str(pdf)})
    assert info["ok"] is True
    assert info.get("pdf") is True
    st = _result({"op": "files_stat", "path": str(pdf)})
    assert st["ok"] is True
    assert st.get("suffix") == ".pdf"
    assert st.get("pdf") is True

    png = tmp_roots / "x.png"
    png.write_bytes(b"\x89PNG\r\n\x1a\n")
    img = _result({"op": "image_info", "path": str(png)})
    assert img["ok"] is True
    assert img.get("suffix") == ".png"
    st2 = _result({"op": "files_stat", "path": str(png)})
    assert st2.get("image") is True


def test_print_and_dialog_stay_distinct_from_browser_twins():
    from exo_control.ops_catalog import get_op

    assert get_op("print")["op"] == "print"
    assert get_op("browser_print")["op"] == "browser_pdf"
    assert get_op("dialog")["op"] == "dialog"
    assert get_op("browser_dialog")["op"] == "browser_dialog"
    assert "not" in (get_op("print").get("purpose") or "").lower()
    assert "not" in (get_op("dialog").get("purpose") or "").lower()
