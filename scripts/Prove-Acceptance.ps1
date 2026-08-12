#Requires -Version 5.1
<#
.SYNOPSIS
  Acceptance gates for Exo Control (unit + optional live CDP).
.PARAMETER RequireCdp
  Fail if no CDP endpoint is available.
.PARAMETER SkipLive
  Skip live CDP accept script.
#>
param(
  [switch]$RequireCdp,
  [switch]$SkipLive
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
Write-Host "=== Exo Control acceptance ==="
Write-Host "Repo: $root"

Write-Host "`n[1/3] pytest (safety + ops + lease + honesty)..."
python -m pytest tests/test_exo_safety.py tests/test_exo_ops.py tests/test_desktop_lease.py tests/test_honesty_and_ops.py tests/test_window_close_discard.py tests/test_result_envelope.py -q --tb=line
if ($LASTEXITCODE -ne 0) { throw "pytest failed" }

Write-Host "`n[2/3] doctor..."
exo-control doctor
if ($LASTEXITCODE -ne 0) { throw "doctor failed" }

if (-not $SkipLive) {
  Write-Host "`n[3/4] ambient CDP accept (skip-ok if no debugger)..."
  if ($RequireCdp) { $env:EXO_ACCEPT_REQUIRE_CDP = "1" }
  python "$root\scripts\accept_cdp_live.py"
  if ($LASTEXITCODE -ne 0) { throw "accept_cdp_live failed" }
  Write-Host "`n[4/4] Chromium CDP accept (launches browser)..."
  python "$root\scripts\accept_cdp_chromium.py"
  if ($LASTEXITCODE -ne 0) { throw "accept_cdp_chromium failed" }
} else {
  Write-Host "`n[3/3] live CDP skipped (-SkipLive)"
}

Write-Host "`nAcceptance green. See docs/ACCEPTANCE.md for full checklist."
