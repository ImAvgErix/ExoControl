#Requires -Version 5.1
<#
.SYNOPSIS
  Launch Exo Launcher with WebView2 remote debugging for Aether CDP eyes.
  Prefers local Debug build; falls back to installed app under LOCALAPPDATA.
#>
param(
  [int]$Port = 9229
)
$ErrorActionPreference = "Stop"

$preferred = "C:\Users\Erix\Documents\exo-launcher\ExoLauncher\bin\x64\Debug\net10.0-windows10.0.26100.0\win-x64\ExoLauncher.exe"
$fallback = Join-Path $env:LOCALAPPDATA "ExoLauncher\app\ExoLauncher.exe"

if (Test-Path -LiteralPath $preferred) {
  $Exe = $preferred
} elseif (Test-Path -LiteralPath $fallback) {
  $Exe = $fallback
} else {
  throw "Missing ExoLauncher: tried $preferred and $fallback"
}

Get-Process ExoLauncher -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Milliseconds 800

$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = $Exe
$psi.WorkingDirectory = (Split-Path -Parent $Exe)
$psi.UseShellExecute = $false
$psi.EnvironmentVariables["EXO_CDP"] = "1"
$psi.EnvironmentVariables["EXO_CDP_PORT"] = "$Port"
$psi.EnvironmentVariables["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"] = "--remote-debugging-port=$Port"

$proc = [System.Diagnostics.Process]::Start($psi)
if (-not $proc) { throw "Failed to start $Exe" }
Write-Host "Started $Exe (pid $($proc.Id)) with EXO_CDP=1 WEBVIEW2 port $Port"
