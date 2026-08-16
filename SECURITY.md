# Security Policy

Exo Control runs as the logged-in Windows user. It is **not a sandbox**. Anyone who can call MCP / CLI / `ExoExecEngine` has that user's desktop.

`confirm=true` is an **agent assertion**, not a human prompt. It does not widen filesystem roots or steal a lease.

## Trust levels

| Level | How to enable | What changes |
|-------|----------------|--------------|
| **default** | (nothing) | Current safety: confirms, allowroots, rate limits |
| **trusted** | `EXO_TRUST=trusted` | Longer lease TTL, higher rate limits. Confirms still required |
| **full** | Env **and** one-time ack (below) | Owner mode: no Exo policy denials; privileged OS ops auto-elevate via broker |

### Enabling Full-Trust

Full-Trust is explicit. Both gates are required:

1. Human ack (once): `exo-control trust enable --ack "I own this PC"`
   - Writes `~/.exo/state/full_trust.ack` and an audit line in `trust_audit.jsonl`
2. Live switch: set `EXO_TRUST=full` or `EXO_FULL_TRUST=1` on the **MCP/CLI process** and restart it
3. Verify: `exo-control trust status` → `"level": "full"`

Ack without env, or env without ack, stays at **default**. Disable ack with `exo-control trust disable`.

In Full-Trust the AI owns the desktop **and** the OS surface. The MCP process itself is **not** elevated (UIPI would break clicks). Privileged work goes to the `ExoControl\\ElevatedBroker` helper.

## Hard stops

**Every level**

- Human kill-switch file/env (agents cannot disarm it)
- Lease token hidden from `lease_status`
- `browser_eval` when `EXO_DENY_BROWSER_EVAL=1`
- MCP process is never auto-elevated

**Default / trusted only** (lifted in Full-Trust)

- Anti-cheat process names and unnamed PID kill
- Critical Windows services
- HKLM / HKCR / HKU writes
- Writes under Windows / Program Files / ProgramData\\Microsoft
- Non-loopback CDP attach
- `format C:` / `shutdown` style wipe patterns without `confirm=true`

## Default-only gates (relaxed in Full-Trust)

- Recursive delete / HKCU write / named proc kill / non-critical service control / `browser_eval` / dangerous launch / `sleep` / `wifi_connect` / `recycle_empty` / package install / wallpaper set require `confirm=true`
- Paths outside `EXO_FILE_ROOTS` denied unless `EXO_ALLOW_OUTSIDE_ROOTS=1` *and* `confirm=true` (Full-Trust unlocks the disk)
- Unconditional `force_release` unless `EXO_ALLOW_FORCE_RELEASE=1`

## Human kill-switch

Create `~/.exo/KILL` (or `exo-control trust kill`, or `EXO_KILL_SWITCH=1`). All mutating hands fail closed. Clearing the file is operator-only (`exo-control trust kill --clear`). `disarm_kill_switch` cannot override a kill file.

## Operator env (the real gates)

| Env | Default | Meaning |
|-----|---------|---------|
| `EXO_TRUST` | `default` | `default` / `trusted` / `full` |
| `EXO_FULL_TRUST` | off | Shorthand for `EXO_TRUST=full` |
| `EXO_DISABLE_ELEVATE` | off | Skip the admin broker (unit tests) |
| `EXO_FILE_ROOTS` | `~/.exo/workspace` | Allowrooted file ops |
| `EXO_ALLOW_OUTSIDE_ROOTS` | off | Permit `confirm=true` outside roots |
| `EXO_ALLOW_ENV_VALUES` | off | Return secret-like env values |
| `EXO_ALLOW_FORCE_RELEASE` | off | Wipe any lease (also implied by Full-Trust) |
| `EXO_DENY_BROWSER_EVAL` | off | Hard-deny JS eval |
| `EXO_KILL_SWITCH` | off | Arm kill-switch without a file |
| `EXO_MCP_ALIASES` | off | Register `aether_*` MCP tools |
| `EXO_SCREENSHOT_ON_FAIL` | off | Attach JPEG on failed steps |
| `EXO_LEASE_MAX_TTL` | 1800 (8h in Full-Trust if unset) | Max lease seconds |
| `PERPLEXITY_API_KEY` | unset | Enables lease-free `search` / `search_content` (queries leave the machine) |
| `BROWSER_USE_API_KEY` | unset | Enables Browser Use Cloud (`browser_use` / cloud CDP). Traffic leaves the machine |
| `FIRECRAWL_API_KEY` | unset | Enables `scrape` / `crawl` / `site_map` (URLs leave the machine) |
| `BROWSERBASE_API_KEY` / `STAGEHAND_API_KEY` | unset | Enables Stagehand `browser_act` / `stagehand_extract` |
| `SKYVERN_API_KEY` | unset | Enables `skyvern` vision tasks |
| `AGENTQL_API_KEY` | unset | Enables `agentql` page queries |
| `MEM0_API_KEY` | unset | Sends `memory_*` to Mem0 (else local JSONL under state dir) |
| `COMPOSIO_API_KEY` / `MICROSOFT_GRAPH_TOKEN` | unset | Enables `composio` / `mail_list` / `cal_next` / `drive_get` / `todo` / `onenote` / `teams` / `mail_send` / Graph `xlsx` |
| `JINA_API_KEY` | unset | Optional auth for `read_url` (Jina Reader works without it) |
| `GITHUB_TOKEN` / `GH_TOKEN` | unset | Enables `gh_pr` |
| `STEEL_API_KEY` | unset | Enables `steel_start` / `steel_stop` (traffic leaves the machine) |
| `TAVILY_API_KEY` | unset | Enables `tavily` search |
| `EXA_API_KEY` | unset | Enables `exa` search |
| `SLACK_BOT_TOKEN` / `SLACK_TOKEN` | unset | Enables `slack` |
| `NOTION_API_KEY` | unset | Enables `notion` |
| `LINEAR_API_KEY` | unset | Enables `linear` |
| `JIRA_BASE` / `JIRA_EMAIL` / `JIRA_API_TOKEN` | unset | Enables `jira` |
| `DISCORD_BOT_TOKEN` | unset | Enables `discord` |
| `AIRTABLE_API_KEY` | unset | Enables `airtable` |
| `TRELLO_KEY` / `TRELLO_TOKEN` | unset | Enables `trello` |
| `ASANA_ACCESS_TOKEN` | unset | Enables `asana` |
| `TELEGRAM_BOT_TOKEN` | unset | Enables `telegram` |
| `SERPER_API_KEY` | unset | Enables `serper` |
| `BRAVE_API_KEY` | unset | Enables `brave` |
| `OMNIPARSER_URL` | unset | Local OmniParser HTTP for `omni` |
| `EVERYTHING_URL` | `http://127.0.0.1` | Everything HTTP; miss falls back to allowroot walk |
| `SCREENPIPE_URL` | `http://127.0.0.1:3030` | Screenpipe `recall` (loopback) |
| `EXO_ALLOW_REMOTE_CDP` | off | Permit non-loopback CDP that is not Browser Use |
## Reporting

Open a private security advisory on this repo, or contact the maintainer (ImAvgErix) via GitHub.

## Lease model

Desktop hands require an acquired lease. In default/trusted, agents share the machine; they do not own it. Same-agent acquire renews. Foreign force-release is audited and operator-gated.

In Full-Trust the holder owns the desktop for the lease TTL (auto-renewed on hands). Release or expiry returns the machine to a shared state.

## Confirm gates

Destructive ops (kill process, registry write, service start/stop/restart, recursive wipe, `browser_eval`, shell/script launch, `mail_send` / `mail_reply` / `cal_add` / `todo_add` / `drive_put`, volume set, recycle empty, Slack/Discord/Telegram post, `pwsh`, WSL exec, docker run/rm, `print`, `dialog`, power sleep, lnk create, unzip, sqlite writes, `lock_pc`, cookie values) require `confirm=true` in default/trusted. Full-Trust makes those optional except wipe/shutdown patterns and everything in the hard-stop list. Confirm never means "entire disk." No LSASS dump, UAC bypass, anti-cheat kill, or captcha farms.
