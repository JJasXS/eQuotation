# Copy updated eQuotation files from this repo to the production service folder (C:\Apps\eQuotation).
# Run, then restart ProAcc_eQuotation (Admin): net stop ProAcc_eQuotation; net start ProAcc_eQuotation

$ErrorActionPreference = 'Stop'
$src = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$dst = 'C:\Apps\eQuotation'

if (-not (Test-Path $dst)) {
    Write-Error "Service folder not found: $dst"
}

$files = @(
    'main.py',
    'utils\sql_api_projects.py',
    'utils\sql_api_supplier.py',
    'utils\procurement_pr_sql_api.py',
    'utils\procurement_purchase_request.py',
    'utils\stock_items_catalog.py',
    'templates\precurement\precurement.html',
    'static\css\precurement.css'
)

foreach ($rel in $files) {
    $from = Join-Path $src $rel
    $to = Join-Path $dst $rel
    if (-not (Test-Path $from)) {
        Write-Warning "Skip missing: $from"
        continue
    }
    $dir = Split-Path $to -Parent
    if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
    Copy-Item -Path $from -Destination $to -Force
    Write-Host "Copied $rel"
}

Write-Host ""
Write-Host "Deploy done. Restart service (Admin PowerShell):"
Write-Host "  net stop ProAcc_eQuotation"
Write-Host "  Start-Sleep -Seconds 4"
Write-Host "  net start ProAcc_eQuotation"
