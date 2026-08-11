# Copy updated eQuotation files from this repo to the production service folder (C:\Apps\eQuotation).
# Run, then restart ProAcc_eQuotation (Admin): net stop ProAcc_eQuotation; net start ProAcc_eQuotation

$ErrorActionPreference = 'Stop'
$src = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$dst = 'C:\Apps\eQuotation'

if (-not (Test-Path $dst)) {
    Write-Error "Service folder not found: $dst"
}

$files = @(
    # App entry / APIs
    'main.py',
    'api\routes\purchase_requests.py',
    'api\routes\suppliers.py',

    # Utils
    'utils\quotation_api.py',
    'utils\sql_api_projects.py',
    'utils\sql_api_supplier.py',
    'utils\sql_api_customer.py',
    'utils\procurement_pr_sql_api.py',
    'utils\procurement_purchase_request.py',
    'utils\procurement_purchase_order_transfer.py',
    'utils\procurement_bidding.py',
    'utils\procurement_pr_split.py',
    'utils\procurement_sql_api_sync.py',
    'utils\stock_items_catalog.py',

    # Templates
    'templates\precurement\precurement.html',
    'templates\adminBidding.html',
    'templates\supplierBidding.html',
    'templates\createQuotation.html',
    'templates\components\hamburger_menu.html',

    # Static CSS / JS
    'static\css\eq-line-tabs.css',
    'static\css\precurement.css',
    'static\css\supplierBidding.css',
    'static\css\adminBidding.css',
    'static\css\hamburger_menu.css',
    'static\js\hamburger_menu.js',
    'static\js\orderQuotation.js',
    'static\js\viewQuotation.js',
    'static\js\adminViewQuotations.js'
)

$copied = 0
$skipped = 0
foreach ($rel in $files) {
    $from = Join-Path $src $rel
    $to = Join-Path $dst $rel
    if (-not (Test-Path $from)) {
        Write-Warning "Skip missing: $from"
        $skipped++
        continue
    }
    $dir = Split-Path $to -Parent
    if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
    Copy-Item -Path $from -Destination $to -Force
    Write-Host "Copied $rel"
    $copied++
}

Write-Host ""
Write-Host "Deploy done. Copied=$copied skipped=$skipped"
Write-Host "Restart service (Admin PowerShell):"
Write-Host "  net stop ProAcc_eQuotation"
Write-Host "  Start-Sleep -Seconds 4"
Write-Host "  net start ProAcc_eQuotation"
