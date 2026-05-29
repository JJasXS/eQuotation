# Stop ProAcc_eQuotation service and free port 8880, then start dev server.
# Run from repo root or scripts folder; requires Administrator (UAC).

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path

Write-Host 'Stopping ProAcc_eQuotation service...'
sc.exe stop ProAcc_eQuotation | Out-Host
Start-Sleep -Seconds 2

$lines = netstat -ano | Select-String ':8880\s+.*LISTENING'
foreach ($line in $lines) {
    if ($line -match '\s+(\d+)\s*$') {
        $pid = [int]$Matches[1]
        Write-Host "Killing PID $pid on port 8880..."
        taskkill /PID $pid /F 2>$null | Out-Host
    }
}

Start-Sleep -Seconds 1
$check = netstat -ano | Select-String ':8880\s+.*LISTENING'
if ($check) {
    Write-Host 'ERROR: Port 8880 is still in use. Another service may own it.'
    Write-Host $check
    exit 1
}

Write-Host "Starting python main.py in $repoRoot ..."
Set-Location $repoRoot
python main.py
