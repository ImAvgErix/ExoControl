"""
Aether Browser Control Layer

Cross-platform browser automation that works on Windows *today*
(while waiting for ego lite Windows).

Design goals (inspired by ego lite, but practical now):
- Persistent profiles → reuse real logins / cookies when possible
- Structured snapshots (not raw HTML) to save tokens
- Batched-friendly actions
- Multiple independent contexts ("Spaces" analogue)
- Works with any MCP / agent (Grok, Claude Code, Codex, Hermes, etc.)

Uses Playwright. On first use it launches Chromium with a persistent
user-data-dir so sessions survive across agent runs.
"""

from __future__ import annotations

import asyncio
import threading
import base64
import json
import os
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    from playwright.async_api import async_playwright, Browser, BrowserContext, Page, Playwright
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False


def default_profile_dir() -> Path:
    from exo_control.paths import exo_root
    return exo_root() / "browser-profiles" / "default"


@dataclass
class Space:
    """Isolated browser workspace (ego-lite Space analogue)."""
    id: str
    name: str
    context: Any = None  # BrowserContext
    page: Any = None     # Page
    created_at: float = field(default_factory=time.time)


class BrowserEngine:
    """
    Persistent, multi-space browser controller.
    Thread/async safe enough for prototype agent use.
    """

    def __init__(
        self,
        profile_dir: Optional[Path] = None,
        headless: bool = False,
        channel: Optional[str] = None,  # "chrome" | "msedge" | None (bundled chromium)
    ):
        if not HAS_PLAYWRIGHT:
            raise RuntimeError("Playwright not installed. Run: pip install playwright && playwright install chromium")
        self.profile_dir = Path(profile_dir or default_profile_dir())
        self.headless = headless
        self.channel = channel
        self._pw: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._spaces: Dict[str, Space] = {}
        self._default_space_id: Optional[str] = None
        self._lock = asyncio.Lock()
        self._started = False

    async def start(self) -> None:
        if self._started:
            return
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        self._pw = await async_playwright().start()
        launch_args = {
            "user_data_dir": str(self.profile_dir),
            "headless": self.headless,
            "args": [
                "--disable-blink-features=AutomationControlled",
                "--no-first-run",
                "--no-default-browser-check",
            ],
            "viewport": {"width": 1440, "height": 900},
            "ignore_default_args": ["--enable-automation"],
        }
        if self.channel:
            launch_args["channel"] = self.channel
        # Persistent context = one long-lived profile (cookies/logins survive)
        self._browser = await self._pw.chromium.launch_persistent_context(**launch_args)
        self._started = True
        # Create a default space from the first page
        pages = self._browser.pages
        page = pages[0] if pages else await self._browser.new_page()
        sid = "default"
        self._spaces[sid] = Space(id=sid, name="default", context=self._browser, page=page)
        self._default_space_id = sid

    async def stop(self) -> None:
        if self._browser:
            await self._browser.close()
        if self._pw:
            await self._pw.stop()
        self._started = False
        self._spaces.clear()

    async def ensure_started(self) -> None:
        if not self._started:
            await self.start()


    async def _select_cdp_page(self, pages, page_url=None, page_title=None):
        """Prefer Exo / filter match; never silently bind about:blank when a better page exists."""
        if not pages:
            return None, []
        url_f = (page_url or "").strip().lower()
        title_f = (page_title or "").strip().lower()
        ranked = []
        for p in pages:
            try:
                url = (p.url or "").lower()
            except Exception:
                url = ""
            try:
                title = ((await p.title()) or "").lower()
            except Exception:
                title = ""
            score = 0
            reasons = []
            if url_f and url_f in url:
                score += 1000
                reasons.append("url_filter")
            if title_f and title_f in title:
                score += 900
                reasons.append("title_filter")
            elif url_f or title_f:
                # explicit filter present but this page missed — demote hard
                score -= 500
                reasons.append("filter_miss")
            if "app.exo-launcher.local" in url:
                score += 80
                reasons.append("exo_url")
            if "exo launcher" in title:
                score += 70
                reasons.append("exo_title")
            if url.startswith("http://") or url.startswith("https://"):
                if "example.com" not in url:
                    score += 10
            if url.startswith("about:blank") or url == "about:blank":
                score -= 100
                reasons.append("blank")
            if "example.com" in url:
                score -= 50
                reasons.append("example")
            ranked.append((score, p, url, title, reasons))
        ranked.sort(key=lambda x: x[0], reverse=True)
        meta = [
            {"url": u, "title": t, "score": s, "reasons": r}
            for s, _p, u, t, r in ranked[:8]
        ]
        return ranked[0][1], meta

    async def connect_cdp(
        self,
        endpoint: str = "http://127.0.0.1:9222",
        page_url: Optional[str] = None,
        page_title: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Attach to running Chromium/WebView2 debug port; bind Exo page by default."""
        from exo_control.policy import is_loopback_endpoint

        if not HAS_PLAYWRIGHT:
            return {"ok": False, "error": "playwright missing"}
        if not is_loopback_endpoint(endpoint):
            return {
                "ok": False,
                "error": "cdp_not_loopback",
                "endpoint": endpoint,
                "hint": "only 127.0.0.1 / localhost / ::1 CDP endpoints are allowed",
            }
        if self._pw is None:
            self._pw = await async_playwright().start()
        try:
            browser = await self._pw.chromium.connect_over_cdp(endpoint)
            self._cdp_browser = browser
            self._browser = browser.contexts[0] if browser.contexts else await browser.new_context()
            self._started = True
            self._cdp_mode = True
            pages = list(self._browser.pages)
            page, meta = await self._select_cdp_page(
                pages, page_url=page_url, page_title=page_title
            )
            if page is None:
                page = await self._browser.new_page()
                meta = []
            sid = "cdp-default"
            self._spaces[sid] = Space(id=sid, name="cdp-default", context=self._browser, page=page)
            self._default_space_id = sid
            try:
                bound_url = page.url
                bound_title = await page.title()
            except Exception:
                bound_url, bound_title = "", ""
            return {
                "ok": True,
                "endpoint": endpoint,
                "space_id": sid,
                "pages": len(pages),
                "bound_url": bound_url,
                "bound_title": bound_title,
                "page_pick": meta,
                "page_url": page_url,
                "page_title": page_title,
                "browser_runtime": "sticky-loop-v1",
                "sticky_loop": True,
            }
        except Exception as e:
            return {"ok": False, "error": str(e), "hint": "Ensure remote debugging port is listening"}

    async def list_spaces(self) -> List[Dict[str, Any]]:
        await self.ensure_started()
        out = []
        for s in self._spaces.values():
            url = ""
            title = ""
            try:
                if s.page and not s.page.is_closed():
                    url = s.page.url
                    title = await s.page.title()
            except Exception:
                pass
            out.append({"id": s.id, "name": s.name, "url": url, "title": title})
        return out

    async def create_space(
        self,
        name: Optional[str] = None,
        url: Optional[str] = None,
        external: Optional[bool] = None,
    ) -> str:
        """Create a space. When attached via WebView2 debug, external URLs use a
        separate Chromium browser so leftover pages do not pollute the Exo context.
        """
        await self.ensure_started()
        sid = str(uuid.uuid4())[:8]
        name = name or f"space-{sid}"
        use_external = external
        if use_external is None:
            use_external = bool(getattr(self, '_cdp_mode', False))
        if use_external:
            if self._pw is None:
                self._pw = await async_playwright().start()
            ext = getattr(self, "_external_browser", None)
            if ext is None:
                ext = await self._pw.chromium.launch(headless=False)
                self._external_browser = ext
            ctx = await ext.new_context()
            page = await ctx.new_page()
            if url:
                await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            self._spaces[sid] = Space(id=sid, name=name, context=ctx, page=page)
            return sid
        page = await self._browser.new_page()
        if url:
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        self._spaces[sid] = Space(id=sid, name=name, context=self._browser, page=page)
        return sid


    def _get_space(self, space_id: Optional[str] = None) -> Space:
        sid = space_id or self._default_space_id
        if sid not in self._spaces:
            raise ValueError(f"Unknown space: {sid}")
        return self._spaces[sid]

    async def navigate(self, url: str, space_id: Optional[str] = None, wait: str = "domcontentloaded") -> Dict[str, Any]:
        await self.ensure_started()
        space = self._get_space(space_id)
        await space.page.goto(url, wait_until=wait, timeout=60000)
        title = await space.page.title()
        return {"ok": True, "url": space.page.url, "title": title, "space_id": space.id}

    async def screenshot(self, space_id: Optional[str] = None) -> Dict[str, Any]:
        """Return a PNG screenshot for the space (optional structure-miss path)."""
        await self.ensure_started()
        space = self._get_space(space_id)
        page = space.page
        try:
            import base64
            png = await page.screenshot(full_page=False, type="png")
            b64 = base64.b64encode(png).decode("ascii")
            return {
                "ok": True,
                "space_id": space.id,
                "url": page.url,
                "screenshot_base64": b64,
                "bytes": len(png),
            }
        except Exception as e:
            return {"ok": False, "error": str(e), "space_id": getattr(space, "id", space_id)}

    async def snapshot(
        self,
        space_id: Optional[str] = None,
        include_screenshot: bool = False,
        max_text_chars: int = 12000,
    ) -> Dict[str, Any]:
        """
        Structured page observation (token-efficient).
        Returns title, url, interactive elements with refs, visible text sample, optional screenshot.
        """
        await self.ensure_started()
        space = self._get_space(space_id)
        page = space.page

        title = await page.title()
        url = page.url

        # Collect interactive elements with stable-ish refs
        elements = await page.evaluate("""() => {
            const out = [];
            const sel = 'a, button, input, textarea, select, [role="button"], [role="link"], [onclick], [tabindex]';
            const nodes = Array.from(document.querySelectorAll(sel)).slice(0, 80);
            nodes.forEach((el, i) => {
                const rect = el.getBoundingClientRect();
                if (rect.width < 2 || rect.height < 2) return;
                const isPw = (el.getAttribute('type') || '').toLowerCase() === 'password';
                const rawText = (el.innerText || el.value || el.getAttribute('aria-label') || el.getAttribute('placeholder') || '').trim().slice(0, 120);
                const text = isPw ? '••••' : rawText;
                out.push({
                    ref: i,
                    tag: el.tagName.toLowerCase(),
                    type: el.getAttribute('type') || null,
                    password: isPw || undefined,
                    role: el.getAttribute('role') || null,
                    text: text,
                    name: el.getAttribute('name') || null,
                    href: el.getAttribute('href') || null,
                    bbox: [Math.round(rect.x), Math.round(rect.y), Math.round(rect.x+rect.width), Math.round(rect.y+rect.height)]
                });
            });
            return out;
        }""")

        # Visible text sample
        text = await page.evaluate(f"""() => {{
            const t = document.body ? document.body.innerText : '';
            return t.slice(0, {max_text_chars});
        }}""")

        result: Dict[str, Any] = {
            "space_id": space.id,
            "url": url,
            "title": title,
            "elements": elements,
            "text_sample": text,
            "element_count": len(elements),
        }

        if include_screenshot:
            try:
                png = await page.screenshot(type="jpeg", quality=65, full_page=False)
                result["screenshot_base64"] = base64.b64encode(png).decode("ascii")
                result["screenshot_format"] = "jpeg"
            except Exception as e:
                result["screenshot_error"] = str(e)

        return result

    async def _resolve_text_ref(self, page, needle: str) -> Optional[Dict[str, Any]]:
        """Snapshot interactive nodes and pick best text/name/aria match (UIA-like)."""
        needle_l = (needle or "").strip().lower()
        if not needle_l:
            return None
        synonyms = {
            "home library": ("home library", "library"),
            "library": ("library", "home library"),
            "settings": ("settings", "setting", "preferences", "gear"),
            "back": ("back", "go back", "arrow back"),
        }
        needles = list(synonyms.get(needle_l, (needle_l,)))
        if needle_l not in needles:
            needles.insert(0, needle_l)
        elements = await page.evaluate("""() => {
            const out = [];
            const sel = [
              'a', 'button', 'input', 'textarea', 'select',
              '[role="button"]', '[role="link"]', '[role="tab"]', '[role="menuitem"]',
              '[onclick]', '[tabindex]',
              '[aria-label]', '[title]', '[data-tooltip]'
            ].join(',');
            const nodes = Array.from(document.querySelectorAll(sel)).slice(0, 120);
            nodes.forEach((el, i) => {
                const rect = el.getBoundingClientRect();
                // Icon-only chrome buttons can be small but still >= 2px; allow tiny if labeled.
                const aria = el.getAttribute('aria-label') || '';
                const title = el.getAttribute('title') || '';
                const labeled = !!(aria || title || el.getAttribute('placeholder'));
                if (rect.width < 2 || rect.height < 2) {
                    if (!labeled) return;
                }
                const isPw = (el.getAttribute('type') || '').toLowerCase() === 'password';
                const text = isPw ? '••••' : (el.innerText || el.value || aria || el.getAttribute('placeholder') || title || '').trim().slice(0, 120);
                out.push({
                    ref: i,
                    text: text,
                    name: el.getAttribute('name') || '',
                    aria: aria,
                    title: title,
                    placeholder: el.getAttribute('placeholder') || '',
                    role: el.getAttribute('role') || '',
                    tag: el.tagName.toLowerCase()
                });
            });
            return out;
        }""")
        best = None
        best_score = -1.0
        for el in elements or []:
            blob = " ".join([
                str(el.get("text") or ""),
                str(el.get("name") or ""),
                str(el.get("aria") or ""),
                str(el.get("title") or ""),
                str(el.get("placeholder") or ""),
            ]).lower()
            if not blob:
                continue
            for n in needles:
                if blob == n:
                    score = 100.0
                elif blob.startswith(n) or n.startswith(blob):
                    score = 90.0 - abs(len(blob) - len(n)) * 0.1
                elif n in blob:
                    score = 80.0 - blob.find(n) * 0.01
                else:
                    continue
                # Prefer exact original needle slightly
                if n == needle_l:
                    score += 1.0
                if score > best_score:
                    best_score = score
                    best = {
                        "ref": int(el["ref"]),
                        "text": el.get("text") or el.get("aria") or el.get("title"),
                        "score": round(score, 3),
                        "matched": n,
                    }
        return best

    async def click(self, ref: Optional[int] = None, selector: Optional[str] = None,
                    x: Optional[float] = None, y: Optional[float] = None,
                    space_id: Optional[str] = None,
                    text: Optional[str] = None, name: Optional[str] = None,
                    query: Optional[str] = None) -> Dict[str, Any]:
        await self.ensure_started()
        space = self._get_space(space_id)
        page = space.page
        matched = None
        needle = text or name or query

        if ref is None and needle:
            matched = await self._resolve_text_ref(page, str(needle))
            if matched is None:
                # Playwright text click fallback
                try:
                    loc = page.get_by_text(str(needle), exact=False)
                    if await loc.count() > 0:
                        await loc.first.click(timeout=10000)
                        return {"ok": True, "method": "text", "text": str(needle)}
                except Exception:
                    pass
                return {"ok": False, "error": f"No element matching text={needle!r}"}
            ref = int(matched["ref"])

        if ref is not None:
            # Click by element ref from last snapshot
            handle = await page.evaluate_handle(f"""() => {{
                const sel = [
                  'a', 'button', 'input', 'textarea', 'select',
                  '[role="button"]', '[role="link"]', '[role="tab"]', '[role="menuitem"]',
                  '[onclick]', '[tabindex]',
                  '[aria-label]', '[title]', '[data-tooltip]'
                ].join(',');
                const nodes = Array.from(document.querySelectorAll(sel)).slice(0, 120);
                return nodes[{int(ref)}] || null;
            }}""")
            el = handle.as_element()
            if el is None:
                return {"ok": False, "error": f"No element for ref={ref}"}
            await el.click(timeout=10000)
            out = {"ok": True, "method": "text" if matched else "ref", "ref": ref}
            if matched:
                out["matched_text"] = matched.get("text")
                out["score"] = matched.get("score")
            if needle:
                out["query"] = str(needle)
            return out

        if selector:
            await page.click(selector, timeout=10000)
            return {"ok": True, "method": "selector", "selector": selector}

        if x is not None and y is not None:
            await page.mouse.click(x, y)
            return {"ok": True, "method": "coords", "x": x, "y": y}

        return {"ok": False, "error": "Provide ref, text/name, selector, or x/y"}

    async def type_text(self, text: str, ref: Optional[int] = None, selector: Optional[str] = None,
                        clear: bool = False, space_id: Optional[str] = None) -> Dict[str, Any]:
        await self.ensure_started()
        space = self._get_space(space_id)
        page = space.page

        if ref is not None:
            handle = await page.evaluate_handle(f"""() => {{
                const sel = [
                  'a', 'button', 'input', 'textarea', 'select',
                  '[role="button"]', '[role="link"]', '[role="tab"]', '[role="menuitem"]',
                  '[onclick]', '[tabindex]',
                  '[aria-label]', '[title]', '[data-tooltip]'
                ].join(',');
                const nodes = Array.from(document.querySelectorAll(sel)).slice(0, 120);
                return nodes[{int(ref)}] || null;
            }}""")
            el = handle.as_element()
            if el is None:
                return {"ok": False, "error": f"No element for ref={ref}"}
            if clear:
                await el.fill("")
            await el.type(text, delay=20)
            return {"ok": True, "method": "ref", "ref": ref}

        if selector:
            if clear:
                await page.fill(selector, "")
            await page.type(selector, text, delay=20)
            return {"ok": True, "method": "selector", "selector": selector}

        # Type into focused element
        await page.keyboard.type(text, delay=20)
        return {"ok": True, "method": "focused"}

    async def press(self, key: str, space_id: Optional[str] = None) -> Dict[str, Any]:
        await self.ensure_started()
        space = self._get_space(space_id)
        await space.page.keyboard.press(key)
        return {"ok": True, "key": key}

    async def scroll(self, dy: int = 600, space_id: Optional[str] = None) -> Dict[str, Any]:
        await self.ensure_started()
        space = self._get_space(space_id)
        await space.page.mouse.wheel(0, dy)
        return {"ok": True, "dy": dy}

    async def evaluate(self, js: str, space_id: Optional[str] = None) -> Dict[str, Any]:
        """Run arbitrary JS in the page (powerful escape hatch)."""
        await self.ensure_started()
        space = self._get_space(space_id)
        src = (js or "").strip()
        if not src:
            return {"ok": False, "error": "js required", "result": None}
        # Playwright returns null for bare statements; wrap expressions so values come back.
        wrapped = src
        low = src.lstrip()
        if not (low.startswith("() =>") or low.startswith("function") or low.startswith("async ")):
            # expression form: (() => (<expr>))()
            wrapped = "(() => (%s))()" % src
        try:
            result = await space.page.evaluate(wrapped)
        except Exception:
            # Fallback: treat as function body with return
            try:
                result = await space.page.evaluate("(() => { %s })()" % src)
            except Exception as exc:
                return {"ok": False, "error": str(exc), "result": None}
        return {"ok": True, "result": result, "js": src[:200]}


    async def wait_for(self, text: Optional[str] = None, selector: Optional[str] = None,
                       timeout: float = 15000, space_id: Optional[str] = None,
                       name: Optional[str] = None, query: Optional[str] = None) -> Dict[str, Any]:
        await self.ensure_started()
        space = self._get_space(space_id)
        page = space.page
        needle = text or name or query
        try:
            if selector:
                await page.wait_for_selector(selector, timeout=timeout)
                return {"ok": True, "method": "selector", "selector": selector}
            if needle:
                # Prefer interactive snapshot match, then Playwright text.
                matched = await self._resolve_text_ref(page, str(needle))
                if matched is not None:
                    return {"ok": True, "method": "text", "text": str(needle), "ref": matched["ref"],
                            "matched_text": matched.get("text"), "score": matched.get("score")}
                await page.get_by_text(str(needle), exact=False).first.wait_for(timeout=timeout)
                return {"ok": True, "method": "text", "text": str(needle)}
            return {"ok": False, "error": "need text/name or selector"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    async def fill_form(self, fields: Dict[str, str], space_id: Optional[str] = None) -> Dict[str, Any]:
        """fields: {css_selector_or_label: value}. Tries selector first, then placeholder/label text."""
        await self.ensure_started()
        space = self._get_space(space_id)
        page = space.page
        results = []
        for key, value in fields.items():
            try:
                # try as selector
                loc = page.locator(key)
                if await loc.count() > 0:
                    await loc.first.fill(str(value))
                    results.append({"field": key, "ok": True, "method": "selector"})
                    continue
            except Exception:
                pass
            try:
                loc = page.get_by_label(key, exact=False)
                if await loc.count() > 0:
                    await loc.first.fill(str(value))
                    results.append({"field": key, "ok": True, "method": "label"})
                    continue
            except Exception:
                pass
            try:
                loc = page.get_by_placeholder(key, exact=False)
                if await loc.count() > 0:
                    await loc.first.fill(str(value))
                    results.append({"field": key, "ok": True, "method": "placeholder"})
                    continue
            except Exception:
                pass
            results.append({"field": key, "ok": False, "error": "not found"})
        return {"ok": all(r.get("ok") for r in results), "results": results}

    async def close_space(self, space_id: str) -> Dict[str, Any]:
        if space_id == "default":
            return {"ok": False, "error": "Cannot close default space"}
        space = self._spaces.get(space_id)
        if not space:
            return {"ok": False, "error": "Unknown space"}
        try:
            if space.page and not space.page.is_closed():
                await space.page.close()
        except Exception:
            pass
        del self._spaces[space_id]
        return {"ok": True, "closed": space_id}


# Synchronous wrapper for MCP / simple agents
STICKY_LOOP_BUILD = "sticky-loop-v1"


class BrowserEngineSync:
    """Sync façade with a dedicated long-lived asyncio loop thread.

    Playwright CDP/page objects are bound to the loop that created them.
    Calling asyncio.run() per op closes that loop and the next op dies with
    NoneType.send — so every coroutine rides one sticky loop for the engine life.
    """

    def __init__(self, **kwargs):
        self._engine = BrowserEngine(**kwargs)
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._ready = threading.Event()
        self._lock = threading.Lock()

    def _ensure_loop(self) -> asyncio.AbstractEventLoop:
        with self._lock:
            if self._loop is not None and self._loop.is_running():
                return self._loop
            self._ready.clear()

            def _runner() -> None:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                self._loop = loop
                self._ready.set()
                loop.run_forever()

            self._thread = threading.Thread(
                target=_runner, name="aether-browser-loop", daemon=True
            )
            self._thread.start()
        if not self._ready.wait(timeout=5.0):
            raise RuntimeError("browser event loop failed to start")
        assert self._loop is not None
        return self._loop

    def _run(self, coro):
        loop = self._ensure_loop()
        fut = asyncio.run_coroutine_threadsafe(coro, loop)
        return fut.result(timeout=120)

    @property
    def loop_id(self) -> int:
        """Test helper: identity of the sticky loop."""
        loop = self._ensure_loop()
        return id(loop)

    def start(self):
        return self._run(self._engine.start())

    def connect_cdp(
        self,
        endpoint: str = "http://127.0.0.1:9222",
        page_url: Optional[str] = None,
        page_title: Optional[str] = None,
    ) -> Dict[str, Any]:
        return self._run(
            self._engine.connect_cdp(endpoint, page_url=page_url, page_title=page_title)
        )


    def list_spaces(self):
        return self._run(self._engine.list_spaces())

    def create_space(
        self,
        name: Optional[str] = None,
        url: Optional[str] = None,
        external: Optional[bool] = None,
    ):
        return self._run(
            self._engine.create_space(name=name, url=url, external=external)
        )


    def navigate(self, url: str, space_id: Optional[str] = None, wait: str = "domcontentloaded"):
        return self._run(self._engine.navigate(url, space_id, wait))

    def snapshot(self, space_id: Optional[str] = None, include_screenshot: bool = True):
        return self._run(self._engine.snapshot(space_id, include_screenshot))

    def click(self, ref: Optional[int] = None, selector: Optional[str] = None,
              x: Optional[float] = None, y: Optional[float] = None, space_id: Optional[str] = None,
              text: Optional[str] = None, name: Optional[str] = None, query: Optional[str] = None):
        return self._run(self._engine.click(
            ref, selector, x, y, space_id, text=text, name=name, query=query
        ))

    def type_text(self, text: str, ref: Optional[int] = None, selector: Optional[str] = None,
                  clear: bool = False, space_id: Optional[str] = None):
        return self._run(self._engine.type_text(text, ref, selector, clear, space_id))

    def press(self, key: str, space_id: Optional[str] = None):
        return self._run(self._engine.press(key, space_id))

    def scroll(self, dy: int = 600, space_id: Optional[str] = None):
        return self._run(self._engine.scroll(dy, space_id))

    def evaluate(self, js: str, space_id: Optional[str] = None):
        return self._run(self._engine.evaluate(js, space_id))

    def wait_for(self, text=None, selector=None, timeout: float = 15000, space_id=None,
                 name=None, query=None):
        # Accept seconds (<=300) or ms (>300); Playwright needs ms.
        t = float(timeout)
        timeout_ms = t * 1000.0 if t <= 300 else t
        return self._run(self._engine.wait_for(
            text=text, selector=selector, timeout=timeout_ms, space_id=space_id, name=name, query=query
        ))

    def fill_form(self, fields, space_id=None):
        return self._run(self._engine.fill_form(fields, space_id=space_id))

    def close_space(self, space_id: str):
        return self._run(self._engine.close_space(space_id))

    def stop(self):
        try:
            if self._loop is not None and self._loop.is_running():
                return self._run(self._engine.stop())
        finally:
            loop = self._loop
            if loop is not None and loop.is_running():
                loop.call_soon_threadsafe(loop.stop)
            t = self._thread
            if t is not None and t.is_alive():
                t.join(timeout=3.0)
            self._loop = None
            self._thread = None
