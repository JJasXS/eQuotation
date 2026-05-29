# Start eQuotation from repo on a dev port (default 8881).
# Production service often uses 8880 — leave it running and use this script for local dev.
#
# Usage:
#   .\scripts\run-dev.ps1
#   .\scripts\run-dev.ps1 -Port 8882
#   $env:TENANT_CODE='TNT10004'; .\scripts\run-dev.ps1

param(
    [int]$Port = 0
)

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path

if ($Port -le 0) {
    $envPort = ($env:FLASK_PORT -as [int])
    $Port = if ($envPort -gt 0) { $envPort } else { 8881 }
}

function Stop-ListenerOnPort([int]$listenPort) {
    $pattern = ":$listenPort\s+.*LISTENING"
    $lines = netstat -ano | Select-String $pattern
    foreach ($line in $lines) {
        if ($line -match '\s+(\d+)\s*$') {
            $procId = [int]$Matches[1]
            Write-Host "Freeing port $listenPort (PID $procId)..."
            taskkill /PID $procId /F 2>$null | Out-Host
        }
    }
    Start-Sleep -Seconds 1
    $still = netstat -ano | Select-String $pattern
    if ($still) {
        Write-Host "ERROR: Port $listenPort is still in use (may need Administrator to stop the Windows service on 8880)."
        Write-Host $still
        exit 1
    }
}

Stop-ListenerOnPort -listenPort $Port

$env:FLASK_PORT = "$Port"
$env:FLASK_HOST = if ($env:FLASK_HOST) { $env:FLASK_HOST } else { '0.0.0.0' }
if (-not $env:TENANT_CODE) { $env:TENANT_CODE = 'TNT10004' }

Write-Host ""
Write-Host "Dev server: http://localhost:$Port/"
Write-Host "View PR:    http://localhost:$Port/admin/procurement?tab=view"
Write-Host "API docs:   http://localhost:$Port/eq-sql-api/docs"
Write-Host "(Production may still be on http://localhost:8880 via ProAcc_eQuotation service)"
Write-Host ""

Set-Location $repoRoot
python main.py
