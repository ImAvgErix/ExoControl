"""High-level web expert under the same lease / trust model.

Default path is structure-first (CDP/Playwright refs) — compact, no LLM.
Optional extra ``browser-use`` (MIT) can run a goal as a web sub-agent when
installed and an LLM key is present.
"""
from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional, Sequence

try:
    import browser_use  # type: ignore  # noqa: F401
    HAS_BROWSER_USE = True
except Exception:
    HAS_BROWSER_USE = False


_URL_RE = re.compile(r"https?://[^\s]+", re.I)
_CLICK_RE = re.compile(r"\bclick(?:\s+on)?\s+[\"']([^\"']+)[\"']", re.I)
_CLICK_BARE_RE = re.compile(r"\bclick(?:\s+on)?\s+([A-Za-z0-9][\w .:-]{1,80})", re.I)
_TYPE_RE = re.compile(r"\btype\s+[\"']([^\"']+)[\"'](?:\s+into\s+[\"']([^\"']+)[\"'])?", re.I)
_WAIT_RE = re.compile(r"\bwait(?:\s+for)?\s+[\"']([^\"']+)[\"']", re.I)


def browser_use_available() -> bool:
    return HAS_BROWSER_USE


def parse_goal_actions(goal: str, *, url: Optional[str] = None) -> List[Dict[str, Any]]:
    """Cheap heuristic planner so a goal can run without an LLM."""
    text = str(goal or "").strip()
    actions: List[Dict[str, Any]] = []
    nav = (url or "").strip()
    if not nav:
        m = _URL_RE.search(text)
        if m:
            nav = m.group(0).rstrip(").,]")
    if nav:
        actions.append({"action": "navigate", "url": nav})
    for m in _CLICK_RE.finditer(text):
        actions.append({"action": "click", "text": m.group(1).strip()})
    if not _CLICK_RE.search(text):
        m = _CLICK_BARE_RE.search(text)
        if m:
            actions.append({"action": "click", "text": m.group(1).strip()})
    m = _TYPE_RE.search(text)
    if m:
        act: Dict[str, Any] = {"action": "type", "text": m.group(1)}
        if m.group(2):
            act["into"] = m.group(2)
        actions.append(act)
    m = _WAIT_RE.search(text)
    if m:
        actions.append({"action": "wait", "text": m.group(1)})
    low = text.lower()
    if "extract" in low or "read page" in low or "summarize" in low:
        actions.append({"action": "extract"})
    if not actions:
        if nav:
            actions.append({"action": "snapshot"})
        else:
            return []
    return actions[:20]


def _compact_trace(rows: List[Dict[str, Any]], *, max_items: int = 12) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for row in rows[:max_items]:
        slim = {"action": row.get("action"), "ok": row.get("ok")}
        if row.get("error"):
            slim["error"] = str(row["error"])[:240]
        if row.get("url"):
            slim["url"] = str(row["url"])[:300]
        if row.get("text"):
            slim["text"] = str(row["text"])[:80]
        if row.get("title"):
            slim["title"] = str(row["title"])[:120]
        out.append(slim)
    return out


def run_structure_actions(
    browser: Any,
    actions: Sequence[Dict[str, Any]],
    *,
    space_id: Optional[str] = None,
    max_actions: int = 20,
) -> Dict[str, Any]:
    """Execute high-level web actions on BrowserEngineSync. One leased step."""
    if browser is None:
        return {"ok": False, "error": "browser engine required"}
    trace: List[Dict[str, Any]] = []
    last_extract: Optional[str] = None
    last_snap: Optional[Dict[str, Any]] = None
    sid = space_id
    n = 0
    for raw in actions:
        if n >= max_actions:
            break
        if not isinstance(raw, dict):
            continue
        action = str(raw.get("action") or raw.get("op") or raw.get("do") or "").lower()
        action = action.replace("browser_", "")
        n += 1
        try:
            if action in {"navigate", "goto", "open"}:
                url = str(raw.get("url") or raw.get("href") or "")
                result = browser.navigate(url, sid, raw.get("wait", "domcontentloaded"))
            elif action in {"click"}:
                result = browser.click(
                    ref=raw.get("ref"),
                    selector=raw.get("selector"),
                    text=raw.get("text") or raw.get("name") or raw.get("query"),
                    name=raw.get("name"),
                    query=raw.get("query"),
                    space_id=sid,
                )
            elif action in {"type", "fill"}:
                into = raw.get("into") or raw.get("query") or raw.get("selector")
                if action == "fill" and isinstance(raw.get("fields"), dict):
                    result = browser.fill_form(raw.get("fields"), sid)
                else:
                    result = browser.type_text(
                        str(raw.get("text") or raw.get("value") or ""),
                        raw.get("ref"),
                        raw.get("selector") or into,
                        bool(raw.get("clear", False)),
                        sid,
                    )
            elif action in {"press", "key"}:
                result = browser.press(str(raw.get("key") or raw.get("keys") or ""), sid)
            elif action in {"wait"}:
                result = browser.wait_for(
                    text=raw.get("text") or raw.get("name") or raw.get("query"),
                    selector=raw.get("selector"),
                    timeout=float(raw.get("timeout", 8)),
                    space_id=sid,
                )
            elif action in {"snapshot", "observe"}:
                result = browser.snapshot(sid, False)
                if isinstance(result, dict):
                    last_snap = result
            elif action in {"extract", "read"}:
                if hasattr(browser, "extract"):
                    result = browser.extract(sid)
                else:
                    snap = browser.snapshot(sid, False)
                    result = {
                        "ok": isinstance(snap, dict),
                        "text": (snap or {}).get("text_sample") if isinstance(snap, dict) else None,
                        "title": (snap or {}).get("title") if isinstance(snap, dict) else None,
                        "url": (snap or {}).get("url") if isinstance(snap, dict) else None,
                    }
                if isinstance(result, dict):
                    last_extract = str(result.get("text") or result.get("text_sample") or "")[:4000]
            elif action in {"scroll"}:
                result = browser.scroll(
                    dy=raw.get("dy", 600),
                    space_id=sid,
                    direction=raw.get("direction"),
                )
            elif action in {"back"}:
                if hasattr(browser, "back"):
                    result = browser.back(sid)
                else:
                    result = {"ok": False, "error": "browser_back not available"}
            elif action in {"forward"}:
                if hasattr(browser, "forward"):
                    result = browser.forward(sid)
                else:
                    result = {"ok": False, "error": "browser_forward not available"}
            elif action in {"select"}:
                if hasattr(browser, "select"):
                    result = browser.select(
                        value=raw.get("value") or raw.get("text"),
                        selector=raw.get("selector"),
                        ref=raw.get("ref"),
                        space_id=sid,
                    )
                else:
                    result = {"ok": False, "error": "browser_select not available"}
            elif action in {"done", "stop"}:
                result = {"ok": True, "done": True}
            else:
                result = {"ok": False, "error": f"unknown web action: {action}"}
        except Exception as exc:
            result = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        row = {"action": action, "ok": bool(isinstance(result, dict) and result.get("ok") is not False)}
        if isinstance(result, dict):
            if result.get("error"):
                row["error"] = result.get("error")
                row["ok"] = False
            if result.get("url"):
                row["url"] = result.get("url")
            if result.get("title"):
                row["title"] = result.get("title")
            if raw.get("text"):
                row["text"] = raw.get("text")
        trace.append(row)
        if not row["ok"] and raw.get("optional") is not True:
            return {
                "ok": False,
                "mode": "structure",
                "completed": n,
                "trace": _compact_trace(trace),
                "error": row.get("error") or f"{action} failed",
                "extract": last_extract,
            }
    return {
        "ok": True,
        "mode": "structure",
        "completed": n,
        "trace": _compact_trace(trace),
        "extract": last_extract,
        "snapshot": (
            {
                "title": last_snap.get("title"),
                "url": last_snap.get("url"),
                "element_count": last_snap.get("element_count") or len(last_snap.get("elements") or []),
            }
            if isinstance(last_snap, dict)
            else None
        ),
    }


def _run_browser_use(goal: str, *, max_steps: int = 20) -> Dict[str, Any]:
    if not HAS_BROWSER_USE:
        return {
            "ok": False,
            "error": "browser-use not installed",
            "hint": 'pip install "exo-control[web]"',
        }
    api_key = (
        os.environ.get("OPENAI_API_KEY")
        or os.environ.get("BROWSER_USE_API_KEY")
        or os.environ.get("ANTHROPIC_API_KEY")
        or ""
    )
    if not api_key:
        return {
            "ok": False,
            "error": "browser-use needs an LLM key (OPENAI_API_KEY or ANTHROPIC_API_KEY)",
            "hint": "use mode=structure with actions[] / a parseable goal, or set a key",
        }
    try:
        from browser_use import Agent  # type: ignore
    except Exception as exc:
        return {"ok": False, "error": f"browser-use import failed: {exc}"}

    llm = None
    try:
        if os.environ.get("OPENAI_API_KEY"):
            try:
                from browser_use.llm import ChatOpenAI  # type: ignore

                llm = ChatOpenAI(model=os.environ.get("EXO_WEB_MODEL") or "gpt-4o-mini")
            except Exception:
                try:
                    from langchain_openai import ChatOpenAI as _LC  # type: ignore

                    llm = _LC(model=os.environ.get("EXO_WEB_MODEL") or "gpt-4o-mini")
                except Exception:
                    llm = None
        if llm is None and os.environ.get("ANTHROPIC_API_KEY"):
            try:
                from browser_use.llm import ChatAnthropic  # type: ignore

                llm = ChatAnthropic(model=os.environ.get("EXO_WEB_MODEL") or "claude-3-5-haiku-latest")
            except Exception:
                llm = None
        if llm is None:
            return {
                "ok": False,
                "error": "could not construct a browser-use LLM client",
                "hint": "use mode=structure or install matching browser-use extras",
            }

        import asyncio

        agent = Agent(task=str(goal), llm=llm)
        max_steps = max(1, min(40, int(max_steps)))

        async def _go():
            if hasattr(agent, "run"):
                try:
                    return await agent.run(max_steps=max_steps)
                except TypeError:
                    return await agent.run()
            return None

        try:
            history = asyncio.run(_go())
        except RuntimeError:
            # already in a loop — fail honestly rather than nest
            return {
                "ok": False,
                "error": "browser-use cannot start a nested event loop here",
                "hint": "use mode=structure",
            }
        final = ""
        urls: List[str] = []
        if history is not None:
            for attr in ("final_result", "extracted_content"):
                fn = getattr(history, attr, None)
                if callable(fn):
                    try:
                        val = fn()
                        if val:
                            final = str(val)[:4000]
                            break
                    except Exception:
                        pass
            urls_fn = getattr(history, "urls", None)
            if callable(urls_fn):
                try:
                    urls = [str(u)[:300] for u in (urls_fn() or [])[-8:]]
                except Exception:
                    urls = []
        return {
            "ok": True,
            "mode": "browser_use",
            "result": final or None,
            "urls": urls,
        }
    except Exception as exc:
        return {"ok": False, "error": f"browser-use failed: {type(exc).__name__}: {exc}"}


def web_task(
    *,
    goal: str = "",
    actions: Optional[Sequence[Dict[str, Any]]] = None,
    url: Optional[str] = None,
    mode: str = "auto",
    browser: Any = None,
    space_id: Optional[str] = None,
    max_actions: int = 20,
) -> Dict[str, Any]:
    """Run a multi-step web job as one op.

    ``mode=structure`` (default/auto without LLM): parse goal + actions on our CDP path.
    ``mode=browser_use``: optional Browser Use sub-agent.
    ``mode=auto``: structure if we can plan; else browser-use if installed.
    """
    mode_l = (mode or "auto").strip().lower().replace("-", "_")
    acts = list(actions or [])
    if not acts and goal:
        acts = parse_goal_actions(goal, url=url)
    elif url and acts and not any(
        str(a.get("action") or "").lower() in {"navigate", "goto", "open"} for a in acts if isinstance(a, dict)
    ):
        acts = [{"action": "navigate", "url": url}, *acts]

    want_bu = mode_l in {"browser_use", "browseruse", "use"}
    if mode_l == "auto" and not acts and goal:
        want_bu = HAS_BROWSER_USE

    if want_bu:
        out = _run_browser_use(goal or url or "", max_steps=max_actions)
        if out.get("ok"):
            return out
        if mode_l != "auto" and not acts:
            return out
        # auto: fall through to structure if we have a plan
        if not acts:
            return out

    if not acts:
        return {
            "ok": False,
            "error": "web_task needs a parseable goal, actions[], or browser-use extra",
            "hint": 'example: {"op":"web_task","url":"https://example.com","actions":[{"action":"extract"}]}',
            "browser_use": HAS_BROWSER_USE,
        }
    if browser is None:
        return {"ok": False, "error": "structure web_task requires a browser engine"}
    result = run_structure_actions(browser, acts, space_id=space_id, max_actions=max_actions)
    if goal:
        result["goal"] = str(goal)[:300]
    return result
