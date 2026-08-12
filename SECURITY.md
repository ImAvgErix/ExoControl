# Security Policy

## Hard stops (will not implement)

- Anti-cheat bypass / kernel tampering
- Credential dumping or silent elevation
- Default-on screenshots, raw HTML dumps, unbounded observe trees
- Registry / service / process-kill mutation without explicit `confirm=true`
- Claiming "full OS control" while files/registry/services are stubs

## Reporting

Open a private security advisory on this repo, or contact the maintainer (ImAvgErix) via GitHub.

## Status

Exo Control is a developer library (pip / MCP / CLI). Prefer import `exo_control`; `aether.*` is a stable technical compat path. Capability bar: [docs/CAPABILITY.md](docs/CAPABILITY.md).

## Lease model

Desktop hands require an acquired lease. Agents share the machine; they do not own it. Force-release is audited.

## Confirm gates

Destructive ops (kill process, registry write, service start/stop/restart, delete outside allowroots, recursive wipe) require `confirm=true`. Denies leave an audit line.
