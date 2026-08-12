#Requires -Version 5.1
<#
.SYNOPSIS
  Tick docs/ACCEPTANCE.md rows that can be automated; print manual prove steps.
.PARAMETER SkipLaunch
  Do not start Exo Launcher / any UI (default: $true).
#>
param(
  [switch]$SkipLaunch = $true
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$env:PYTHONPATH = "src"
Write-Host "=== Exo Control acceptance prove (code gates) ==="
Write-Host "Repo: $root"
Write-Host "SkipLaunch=$SkipLaunch"

& py -3.12 -m pytest tests/test_exo_safety.py tests/test_exo_ops.py tests/test_desktop_lease.py -q --tb=line
if ($LASTEXITCODE -ne 0) { throw "pytest failed" }

Write-Host ""
Write-Host "Automated ticks (when pytest green):"
Write-Host "  [x] verify / wait_change fail-closed (tests)"
Write-Host "  [x] Kill switch arms -> exec blocked, zero injects (tests)"
Write-Host "  [x] Destructive patterns require confirm=true (tests)"
Write-Host "  [x] Multi-agent desktop lease / shared lock (tests)"
Write-Host "  [x] screenshot wrong-window fail (tests)"
Write-Host "  [x] act-without-focus hard fail (tests)"
Write-Host "  [x] launch CDP child env assign (tests)"
Write-Host ""
Write-Host "Manual / live prove:"
Write-Host "  [ ] Launch helper with CDP (SkipLaunch=$SkipLaunch - not run here)"
Write-Host "  [ ] cdp_discover returns live endpoint + page target"
Write-Host "  [ ] browser_snapshot Exo Launcher UI text via CDP"
Write-Host "  [ ] observe/read named controls without screenshot"
Write-Host "  [ ] Cold start: slim MCP status -> observe+click+verify x3"
Write-Host ""
Write-Host "See docs/ACCEPTANCE.md for full checklist."
