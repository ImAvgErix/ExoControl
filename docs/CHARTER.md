# Exo Control — product charter

One page. Capability bar: [CAPABILITY.md](CAPABILITY.md). Product owner: ImAvgErix / Exo family.

## Name & slug

| | |
|--|--|
| **Product** | Exo Control |
| **GitHub** | [ImAvgErix/ExoControl](https://github.com/ImAvgErix/ExoControl) |
| **CLI / package** | `exo-control` / import `exo_control` |
| **Compat module** | `aether.*` (stable technical path; not the public brand) |

Do **not** market or title the product as anything outside the Exo family.

## Positioning

Realtime **desktop / browser / files / registry / OS** control for **any** agent harness — via:

1. **MCP** (slim script-first surface)
2. **CLI**
3. **Python SDK**

Eyes + hands on Windows. Compact-by-default. Structure/DOM first; screenshots only on ask or structure miss. Agents lease the desktop; they do not own it.

## Product promise (token efficiency)

- Compact observe/refs by default (hard size/ref caps)
- Batched multi-step `exec` (one round-trip workflows)
- No screenshot-default; no raw HTML / full-tree dumps unless `verbose`
- Ref-stable acts from the prior observe/snapshot in-script

## Relationship to Exo

| Product | Role |
|--------|------|
| **Exo Launcher** | Calm AMOLED game library (separate repo, ships Setup.exe) |
| **Exo Control** | Hands/eyes stack — works **with** Exo Launcher and any Win app |
| **Exo OS / Hub / Link** | Sibling surface area; Control does not subsume them |

Exo Launcher is a first-class target, not the only one. Control must not require Launcher to be useful.

## Install (library — not an app release)

Exo Control is a **Python package**, not a Windows app installer.

```bash
pip install "git+https://github.com/ImAvgErix/ExoControl.git@v2.1.0"
exo-control doctor
```

There is **no Setup.exe**. Wheels may appear on the GitHub Release; versioning is `pyproject.toml` + git tags.

## Non-goals

- Anti-cheat bypass, kernel tampering, credential dumping, silent elevation
- Replacing store DRM / launcher ownership
- Building the Exo Launcher UI inside this repo
- Cloud agent identity / Exo account / analytics by default
- Voice/listen as a launch blocker
- Shipping as a consumer desktop installer

## License

**MIT** — same as Exo Launcher.

## One-line pitch

**Exo Control — realtime PC eyes and hands for any AI agent. Compact. Leased. Honest.**
