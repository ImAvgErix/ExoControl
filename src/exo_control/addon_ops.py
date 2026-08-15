"""Dispatch table for lease-free addon integrations."""
from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from exo_control import (
    agentql_ops,
    composio_ops,
    everything_ops,
    firecrawl_ops,
    markitdown_ops,
    memory_ops,
    omniparser_ops,
    screenpipe_ops,
    skyvern_ops,
    stagehand_ops,
)

Handler = Callable[[Dict[str, Any]], Dict[str, Any]]

ROUTES: Dict[str, Handler] = {
    "scrape": firecrawl_ops.scrape,
    "firecrawl": firecrawl_ops.scrape,
    "firecrawl_scrape": firecrawl_ops.scrape,
    "crawl": firecrawl_ops.crawl,
    "firecrawl_crawl": firecrawl_ops.crawl,
    "site_map": firecrawl_ops.site_map,
    "map": firecrawl_ops.site_map,
    "firecrawl_map": firecrawl_ops.site_map,
    "files_convert": markitdown_ops.convert,
    "read_doc": markitdown_ops.convert,
    "markitdown": markitdown_ops.convert,
    "stagehand": stagehand_ops.act,
    "browser_act": stagehand_ops.act,
    "stagehand_act": stagehand_ops.act,
    "stagehand_extract": stagehand_ops.extract,
    "browser_extract": stagehand_ops.extract,
    "skyvern": skyvern_ops.run_task,
    "skyvern_task": skyvern_ops.run_task,
    "omni": omniparser_ops.parse,
    "omni_parse": omniparser_ops.parse,
    "omniparser": omniparser_ops.parse,
    "agentql": agentql_ops.query,
    "browser_query": agentql_ops.query,
    "page_query": agentql_ops.query,
    "files_find": everything_ops.find,
    "everything": everything_ops.find,
    "find_files": everything_ops.find,
    "memory_add": memory_ops.add,
    "mem0_add": memory_ops.add,
    "memory_search": memory_ops.search,
    "mem0_search": memory_ops.search,
    "composio": composio_ops.run,
    "composio_run": composio_ops.run,
    "mail_list": composio_ops.mail_list,
    "cal_next": composio_ops.cal_next,
    "drive_get": composio_ops.drive_get,
    "recall": screenpipe_ops.search,
    "screen_search": screenpipe_ops.search,
    "screenpipe": screenpipe_ops.search,
}


def dispatch(op: str, step: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    fn = ROUTES.get(op)
    if fn is None:
        return None
    return fn(step)


def capabilities() -> Dict[str, Any]:
    return {
        "firecrawl": True,
        "firecrawl_configured": firecrawl_ops.configured(),
        "markitdown": True,
        "stagehand": True,
        "stagehand_configured": stagehand_ops.configured(),
        "skyvern": True,
        "skyvern_configured": skyvern_ops.configured(),
        "omniparser": True,
        "omniparser_configured": omniparser_ops.configured(),
        "agentql": True,
        "agentql_configured": agentql_ops.configured(),
        "everything": True,
        "memory": True,
        "mem0_configured": memory_ops.mem0_configured(),
        "composio": True,
        "composio_configured": composio_ops.configured(),
        "screenpipe": True,
    }
