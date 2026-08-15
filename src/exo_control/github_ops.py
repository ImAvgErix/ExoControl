"""GitHub pull-request status (HTTP). Auth: ``GITHUB_TOKEN`` / ``GH_TOKEN``."""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from urllib.parse import quote

from exo_control.http_json import clip_int, env_key, error_from_http, request_json, timeout_of, user_agent
from exo_control.policy import parse_confirm

_REQUEST_JSON = None
API = "https://api.github.com"


def api_key() -> Optional[str]:
    return env_key("GITHUB_TOKEN", "GH_TOKEN", "EXO_GITHUB_TOKEN")


def configured() -> bool:
    return bool(api_key())


def _headers(token: str) -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": user_agent(),
    }


def _call(method: str, url: str, headers: Dict[str, str], payload: Optional[Dict[str, Any]], timeout: float):
    if _REQUEST_JSON is not None:
        return _REQUEST_JSON(method, url, headers, payload, timeout)
    return request_json(method, url, headers, payload, timeout)


def _repo_of(step: Dict[str, Any]) -> str:
    repo = str(step.get("repo") or step.get("repository") or "").strip()
    if repo:
        return repo.strip("/")
    owner = str(step.get("owner") or step.get("org") or "").strip()
    name = str(step.get("name") or step.get("project") or "").strip()
    if owner and name:
        return f"{owner}/{name}"
    return ""


def gh_pr(step: Dict[str, Any]) -> Dict[str, Any]:
    token = api_key()
    if not token:
        return {
            "ok": False,
            "error": "gh_pr requires GITHUB_TOKEN",
            "code": "AUTHENTICATION",
            "hint": "export GITHUB_TOKEN or GH_TOKEN",
        }
    repo = _repo_of(step)
    if not repo or "/" not in repo:
        return {"ok": False, "error": "gh_pr requires repo=owner/name", "code": "MISSING_REPO"}
    number = step.get("number") or step.get("pr") or step.get("id")
    if number is not None and str(number).strip():
        url = f"{API}/repos/{quote(repo, safe='/')}/pulls/{quote(str(number).strip())}"
        status, parsed, raw = _call("GET", url, _headers(token), None, timeout_of(step))
        if status != 200:
            return error_from_http(status, parsed, raw, what="gh_pr")
        return {
            "ok": True,
            "provider": "github",
            "repo": repo,
            "pr": {
                "number": parsed.get("number"),
                "title": parsed.get("title"),
                "state": parsed.get("state"),
                "merged": parsed.get("merged"),
                "draft": parsed.get("draft"),
                "html_url": parsed.get("html_url"),
                "user": (parsed.get("user") or {}).get("login") if isinstance(parsed.get("user"), dict) else None,
            },
        }
    top = clip_int(step.get("max") or step.get("limit") or 5, 5, 1, 20)
    state = str(step.get("state") or "open")
    url = f"{API}/repos/{quote(repo, safe='/')}/pulls?state={quote(state)}&per_page={top}"
    status, parsed, raw = _call("GET", url, _headers(token), None, timeout_of(step))
    if status != 200:
        return error_from_http(status, parsed, raw, what="gh_pr")
    items = parsed.get("value") if isinstance(parsed.get("value"), list) else parsed
    if not isinstance(items, list):
        items = []
    prs = []
    for item in items:
        if isinstance(item, dict):
            prs.append({
                "number": item.get("number"),
                "title": item.get("title"),
                "state": item.get("state"),
                "html_url": item.get("html_url"),
            })
    return {"ok": True, "provider": "github", "repo": repo, "prs": prs, "count": len(prs)}


def _issue_rows(parsed: Any) -> List[Dict[str, Any]]:
    if isinstance(parsed, list):
        items = parsed
    elif isinstance(parsed, dict):
        items = parsed.get("value") or parsed.get("items") or parsed.get("issues") or []
    else:
        items = []
    rows = []
    for item in items:
        if isinstance(item, dict):
            rows.append({
                "number": item.get("number"),
                "title": item.get("title"),
                "state": item.get("state"),
                "html_url": item.get("html_url"),
            })
    return rows


def gh_issue(step: Dict[str, Any]) -> Dict[str, Any]:
    token = api_key()
    if not token:
        return {
            "ok": False,
            "error": "gh_issue requires GITHUB_TOKEN",
            "code": "AUTHENTICATION",
            "hint": "export GITHUB_TOKEN or GH_TOKEN",
        }
    repo = _repo_of(step)
    if not repo or "/" not in repo:
        return {"ok": False, "error": "gh_issue requires repo=owner/name", "code": "MISSING_REPO"}
    title = str(step.get("title") or "").strip()
    if title:
        if not parse_confirm(step.get("confirm", False)):
            return {"ok": False, "error": "gh_issue create requires confirm=true", "code": "CONFIRM_REQUIRED"}
        status, parsed, raw = _call(
            "POST",
            f"{API}/repos/{quote(repo, safe='/')}/issues",
            _headers(token),
            {"title": title, "body": str(step.get("body") or step.get("text") or "")},
            timeout_of(step),
        )
        if status not in {200, 201}:
            return error_from_http(status, parsed, raw, what="gh_issue")
        return {"ok": True, "provider": "github", "repo": repo, "issue": {
            "number": parsed.get("number"), "title": parsed.get("title"), "html_url": parsed.get("html_url"),
        }}
    top = clip_int(step.get("max") or 10, 10, 1, 30)
    state = str(step.get("state") or "open")
    status, parsed, raw = _call(
        "GET",
        f"{API}/repos/{quote(repo, safe='/')}/issues?state={quote(state)}&per_page={top}",
        _headers(token),
        None,
        timeout_of(step),
    )
    if status != 200:
        return error_from_http(status, parsed, raw, what="gh_issue")
    issues = _issue_rows(parsed)
    return {"ok": True, "provider": "github", "repo": repo, "issues": issues, "count": len(issues)}
