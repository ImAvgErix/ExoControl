# Exo Control — product charter

One page. Capability bar: **Jarvis OS** (`aether-driver` → this product). Source: Product.

## Name & slug
- **Product:** Exo Control
- **GitHub:** `ImAvgErix/ExoControl` (match ExoHub / ExoOS / ExoLink PascalCase)
- **PyPI / CLI:** `exo-control` / `exocontrol` (TBD at packaging; prefer `exo-control` CLI)
- Working name "Exo Control" stays; do **not** ship as `aether-driver` publicly

## Positioning
Realtime **desktop / browser / files / registry / OS** control for **any** agent harness — Cursor, Claude, Codex, custom — via:
1. **MCP** (slim script-first surface)
2. **CLI**
3. **Python SDK**

Eyes + hands on Windows. Compact-by-default. Structure/DOM first; screenshots only on ask or structure miss. Agents lease the desktop; they do not own it.

## Product promise (token efficiency)
- Compact observe/refs by default (hard size/ref caps)
- Batched multi-step `exec` (one round-trip workflows)
- No screenshot-default; no raw HTML / full-tree dumps unless `verbose`
- Ref-stable acts from the prior observe/snapshot in-script

If a build regresses these, it fails Jarvis OS P0 — not shippable as Exo Control.

## Relationship to Exo
| Product | Role |
|--------|------|
| **ExoLauncher** | The calm AMOLED game library app (separate repo) |
| **Exo Control** | The hands/eyes stack — works **with** Exo (WebView2 CDP) **and** any Win app |
| **Exo OS / Hub / Link** | Sibling surface area; Control does not subsume them |

Exo is a first-class target, not the only one. Control must not require Exo to be useful.

## Non-goals
- Anti-cheat bypass, kernel tampering, credential dumping, silent elevation
- Replacing store DRM / launcher ownership (same honesty as ExoLauncher AGENTS.md)
- Building the ExoLauncher UI inside this repo
- Cloud agent identity / Exo account / analytics by default
- Voice/listen as a launch blocker

## Capability bar
Ship against **`docs/JARVIS-OS.md`**: Floor (Jarvis + Plus P0) + Jarvis OS P0 (efficiency, UIA, DOM/CDP, files, registry, OS infra). Stamp **Jarvis OS** before calling Exo Control generally available.

## License
**MIT** — same as ExoLauncher / current aether-driver unless Eric overrides.

## Public vs private
- **Recommend public** (Exo family is public; agents need a discoverable harness-agnostic control plane).
- Ship with `SECURITY.md` hard stops + alpha badge until Jarvis OS Floor+P0 are stamped.
- If extract is messy for >1 week, keep the repo **private only for the extract PR window**, then flip public — do not stay private as a product strategy.

## Packaging outcomes (Definition of Ready to announce)
- [ ] Repo `ImAvgErix/ExoControl` with this charter + SECURITY.md + JARVIS-OS.md
- [ ] MCP + CLI + Python SDK install paths documented
- [ ] aether-driver extracted/rebranded; no broken ExoLauncher dependency for core ops
- [ ] Jarvis OS Floor + P0 [x] (Product stamp)
- [ ] Hard stops tested (confirm gates, anti-cheat deny, compact caps)

## One-line pitch
**Exo Control — realtime PC eyes and hands for any AI agent. Compact. Leased. Honest.**
