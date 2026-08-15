# Security Policy

Exo Control runs as the logged-in Windows user. It is **not a sandbox**. Anyone who can call MCP / CLI / `ExoExecEngine` has that user's desktop.

`confirm=true` is an **agent assertion**, not a human prompt. It does not widen filesystem roots or steal a lease.

## Hard stops (enforced in code)

- Anti-cheat process names (fail closed if a kill PID cannot be resolved)
- Critical Windows services
- HKLM registry writes
- Non-loopback CDP attach
- `browser_eval` without `confirm=true` (`EXO_DENY_BROWSER_EVAL=1` hard-denies)
- Recursive delete without `confirm=true`
- Paths outside `EXO_FILE_ROOTS` unless the operator sets `EXO_ALLOW_OUTSIDE_ROOTS=1`
- Secret-like `env_get` values unless `EXO_ALLOW_ENV_VALUES=1`
- Lease token hidden from `lease_status`
- Unconditional `force_release` unless `EXO_ALLOW_FORCE_RELEASE=1`

## Operator env (the real gates)

| Env | Default | Meaning |
|-----|---------|---------|
| `EXO_FILE_ROOTS` | `~/.exo/workspace` | Allowrooted file ops |
| `EXO_ALLOW_OUTSIDE_ROOTS` | off | Permit `confirm=true` outside roots |
| `EXO_ALLOW_ENV_VALUES` | off | Return secret-like env values |
| `EXO_ALLOW_FORCE_RELEASE` | off | Wipe any lease |
| `EXO_DENY_BROWSER_EVAL` | off | Hard-deny JS eval |
| `EXO_MCP_ALIASES` | off | Register `aether_*` MCP tools |
| `EXO_SCREENSHOT_ON_FAIL` | off | Attach JPEG on failed steps |
| `EXO_LEASE_MAX_TTL` | 1800 | Max lease seconds |
| `PERPLEXITY_API_KEY` | unset | Enables lease-free `search` / `search_content` (queries leave the machine) |
| `BROWSER_USE_API_KEY` | unset | Enables Browser Use Cloud (`browser_use` / cloud CDP). Traffic leaves the machine |
| `FIRECRAWL_API_KEY` | unset | Enables `scrape` / `crawl` / `site_map` (URLs leave the machine) |
| `BROWSERBASE_API_KEY` / `STAGEHAND_API_KEY` | unset | Enables Stagehand `browser_act` / `stagehand_extract` |
| `SKYVERN_API_KEY` | unset | Enables `skyvern` vision tasks |
| `AGENTQL_API_KEY` | unset | Enables `agentql` page queries |
| `MEM0_API_KEY` | unset | Sends `memory_*` to Mem0 (else local JSONL under state dir) |
| `COMPOSIO_API_KEY` / `MICROSOFT_GRAPH_TOKEN` | unset | Enables `composio` / `mail_list` / `cal_next` / `drive_get` |
| `OMNIPARSER_URL` | unset | Local OmniParser HTTP for `omni` |
| `EVERYTHING_URL` | `http://127.0.0.1` | Everything HTTP; miss falls back to allowroot walk |
| `SCREENPIPE_URL` | `http://127.0.0.1:3030` | Screenpipe `recall` (loopback) |
| `EXO_ALLOW_REMOTE_CDP` | off | Permit non-loopback CDP that is not Browser Use |

## Reporting

Open a private security advisory on this repo, or contact the maintainer (ImAvgErix) via GitHub.

## Lease model

Desktop hands require an acquired lease. Agents share the machine; they do not own it. Same-agent acquire renews. Foreign force-release is audited and operator-gated.

## Confirm gates

Destructive ops (kill process, registry write, service start/stop/restart, recursive wipe, `browser_eval`, shell/script launch) require `confirm=true`. Denies leave an audit line. Confirm never means "entire disk."
