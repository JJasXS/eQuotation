# Run this script in PowerShell **as Administrator** to restart the production eQuotation service.
# Replaces old code on port 8880 (ProAcc_eQuotation) without leaving P1-P5 project fallbacks.

$ErrorActionPreference = 'Stop'

Write-Host "Stopping ProAcc_eQuotation..."
net stop ProAcc_eQuotation

Start-Sleep -Seconds 3

Write-Host "Starting ProAcc_eQuotation..."
net start ProAcc_eQuotation

Start-Sleep -Seconds 2
netstat -ano | findstr ":8880.*LISTENING"

Write-Host ""
Write-Host "Done. Hard-refresh browser: http://localhost:8880/admin/procurement"
Write-Host "Project dropdown should come from SQL API GET /project/* (e.g. NON-PROJECT), not P1-P5."
