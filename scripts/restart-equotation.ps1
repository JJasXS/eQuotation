# Stop whatever is listening on FLASK_PORT (default 8880) and start eQuotation with current code.
# Usage:
#   .\scripts\restart-equotation.ps1
#   .\scripts\restart-equotation.ps1 -Port 8881

param(
    [int]$Port = 0
)

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path

if ($Port -le 0) {
    $envPort = ($env:FLASK_PORT -as [int])
    $Port = if ($envPort -gt 0) { $envPort } else { 8880 }
}

function Stop-ListenerOnPort([int]$listenPort) {
    $pattern = ":$listenPort\s+.*LISTENING"
    $lines = netstat -ano | Select-String $pattern
    if (-not $lines) {
        Write-Host "Port $listenPort is free."
        return
    }
    foreach ($line in $lines) {
        if ($line -match '\s+(\d+)\s*$') {
            $procId = [int]$Matches[1]
            Write-Host "Stopping PID $procId on port $listenPort..."
            taskkill /PID $procId /F 2>$null | Out-Host
        }
    }
    Start-Sleep -Seconds 2
}

Stop-ListenerOnPort -listenPort $Port

$env:FLASK_PORT = "$Port"
$env:FLASK_HOST = if ($env:FLASK_HOST) { $env:FLASK_HOST } else { '0.0.0.0' }
if (-not $env:TENANT_CODE) { $env:TENANT_CODE = 'TNT10004' }

# Do not use legacy project fallbacks (P1–P5); projects come from SQL API GET /project/* only.
Remove-Item Env:PROJECT_CODE_FALLBACK -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "Starting eQuotation on http://localhost:$Port/ (TENANT_CODE=$($env:TENANT_CODE))"
Write-Host "After start, hard-refresh Create e-PR in the browser (Ctrl+Shift+R)."
Write-Host ""

Set-Location $repoRoot
python main.py
