"""Unit tests for CDP page preference (Exo over about:blank)."""
from __future__ import annotations

import asyncio

from aether.browser import BrowserEngine


class FakePage:
    def __init__(self, url: str, title: str = ""):
        self.url = url
        self._title = title

    async def title(self) -> str:
        return self._title


def test_select_prefers_exo_over_blank_and_example():
    eng = BrowserEngine.__new__(BrowserEngine)
    pages = [
        FakePage("about:blank", ""),
        FakePage("https://example.com/", "Example Domain"),
        FakePage("https://app.exo-launcher.local/", "Exo Launcher"),
        FakePage("about:blank", "blank2"),
    ]
    page, meta = asyncio.run(eng._select_cdp_page(pages))
    assert page is pages[2]
    assert "app.exo-launcher.local" in page.url
    assert meta[0]["score"] >= meta[1]["score"]


def test_select_honors_page_url_filter():
    eng = BrowserEngine.__new__(BrowserEngine)
    pages = [
        FakePage("https://app.exo-launcher.local/", "Exo Launcher"),
        FakePage("https://news.ycombinator.com/", "Hacker News"),
    ]
    page, meta = asyncio.run(eng._select_cdp_page(pages, page_url="ycombinator"))
    assert page is pages[1]


def test_select_honors_title_filter():
    eng = BrowserEngine.__new__(BrowserEngine)
    pages = [
        FakePage("https://app.exo-launcher.local/settings", "Exo Launcher"),
        FakePage("https://app.exo-launcher.local/library", "Library"),
    ]
    page, _ = asyncio.run(eng._select_cdp_page(pages, page_title="library"))
    assert page is pages[1]


def test_blank_only_still_returns_a_page():
    eng = BrowserEngine.__new__(BrowserEngine)
    pages = [FakePage("about:blank", ""), FakePage("about:blank", "x")]
    page, meta = asyncio.run(eng._select_cdp_page(pages))
    assert page is not None
    assert all(m["score"] < 0 for m in meta)
