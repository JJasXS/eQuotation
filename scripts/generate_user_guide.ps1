# Generate eQuotation user guide assets (screenshots + confirm docs).
#
# Usage:
#   .\scripts\generate_user_guide.ps1
#   .\scripts\generate_user_guide.ps1 -Port 8881
#
# Steps:
#   1) Ensure app is reachable on Port (start run-dev.ps1 in background if needed)
#   2) Capture screenshots via scripts/capture_user_guide_screens.py
#   3) Confirm docs/USER_GUIDE.md and docs/USER_GUIDE_FOR_GOOGLE_DOCS.txt exist

param(
    [int]$Port = 8881,
    [int[]]$FallbackPorts = @(8880)
)

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$imgDir = Join-Path $repoRoot 'docs\images\user-guide'
$guideMd = Join-Path $repoRoot 'docs\USER_GUIDE.md'
$guideTxt = Join-Path $repoRoot 'docs\USER_GUIDE_FOR_GOOGLE_DOCS.txt'
$startedServer = $false
$serverProc = $null

function Resolve-EqPython {
    $candidates = @(
        (Join-Path $repoRoot 'venv\Scripts\python.exe'),
        (Join-Path $repoRoot '.venv\Scripts\python.exe'),
        (Join-Path $repoRoot '.venv312\Scripts\python.exe'),
        'C:\Apps\eQuotation\venv\Scripts\python.exe'
    )
    foreach ($c in $candidates) {
        if ($c -and (Test-Path $c)) {
            try {
                & $c -c "import flask" 2>$null
                if ($LASTEXITCODE -eq 0) { return $c }
            } catch { }
        }
    }
    return 'python'
}

function Test-EqReachable([string]$url) {
    try {
        $resp = Invoke-WebRequest -Uri "$url/login" -UseBasicParsing -TimeoutSec 5
        return ($resp.StatusCode -ge 200 -and $resp.StatusCode -lt 500)
    } catch {
        return $false
    }
}

$py = Resolve-EqPython
$baseUrl = "http://127.0.0.1:$Port"
$env:EQ_GUIDE_CAPTURE = '1'
if (-not $env:TENANT_CODE) { $env:TENANT_CODE = 'TNT10004' }

Write-Host "=== eQuotation user-guide generator ==="
Write-Host "Repo:   $repoRoot"
Write-Host "Port:   $Port"
Write-Host "Python: $py"
Write-Host "EQ_GUIDE_CAPTURE=1"
Write-Host ""

New-Item -ItemType Directory -Force -Path $imgDir | Out-Null

function Stop-ListenerOnPort([int]$listenPort) {
    $pattern = ":$listenPort\s+.*LISTENING"
    $lines = netstat -ano | Select-String $pattern
    foreach ($line in $lines) {
        if ($line -match '\s+(\d+)\s*$') {
            $procId = [int]$Matches[1]
            Write-Host "Stopping PID $procId on port $listenPort..."
            taskkill /PID $procId /F 2>$null | Out-Host
        }
    }
    Start-Sleep -Seconds 2
}

function Start-EqGuideServer([int]$listenPort) {
    $env:FLASK_PORT = "$listenPort"
    $env:FLASK_HOST = if ($env:FLASK_HOST) { $env:FLASK_HOST } else { '0.0.0.0' }
    $env:EQ_GUIDE_CAPTURE = '1'
    $env:FLASK_DEBUG = if ($env:FLASK_DEBUG) { $env:FLASK_DEBUG } else { 'true' }
    Write-Host "Starting python main.py on $listenPort (EQ_GUIDE_CAPTURE=1)..."
    $proc = Start-Process -FilePath $py `
        -ArgumentList @('main.py') `
        -WorkingDirectory $repoRoot `
        -PassThru `
        -WindowStyle Minimized
    $url = "http://127.0.0.1:$listenPort"
    for ($i = 1; $i -le 45; $i++) {
        Start-Sleep -Seconds 2
        if (Test-EqReachable $url) {
            Write-Host "App ready after ~$($i * 2)s on $listenPort"
            return $proc
        }
        Write-Host "  waiting for $url/login ($i/45)..."
    }
    return $null
}

function Test-GuideCaptureLogin([string]$url) {
    try {
        $body = '{"role":"admin","email":"guide-admin@local"}'
        $resp = Invoke-WebRequest -Uri "$url/api/guide_capture_login" -Method POST -Body $body -ContentType 'application/json' -UseBasicParsing -TimeoutSec 8
        return ($resp.StatusCode -eq 200)
    } catch {
        return $false
    }
}

# --- Ensure docs exist (create stubs if missing) ---
if (-not (Test-Path $guideMd)) {
    Write-Host "Creating docs/USER_GUIDE.md ..."
    @'
# ProAcc eQuotation User Guide

This guide walks through the main screens of ProAcc eQuotation.

## Sign in

![Login](images/user-guide/01-login.png)

1. Open the login page.
2. Choose account type: Customer, Admin / staff, or Supplier.
3. Enter your email and continue to receive a one-time password (OTP).
4. Guests can use **Sign in as Guest**.

![Guest sign-in](images/user-guide/02-guest-signin.png)

## Admin dashboard

![Admin dashboard](images/user-guide/03-admin-dashboard.png)

After admin login, open the dashboard to reach quotations, procurement, approvals, and reports.

## Create quotation

![Create quotation](images/user-guide/04-create-quotation.png)

Build a sales quotation: pick customer, add lines, review totals, then submit.

## My quotations

![My quotations](images/user-guide/05-my-quotations.png)

Customers can review quotations they created.

## Admin view quotations

![Admin view quotations](images/user-guide/06-admin-view-quotations.png)

Staff can search and open company quotations.

## Procurement

### View purchase requests

![Procurement view PR](images/user-guide/07-procurement-view-pr.png)

### Create purchase request

![Procurement create PR](images/user-guide/08-procurement-create-pr.png)

## Bidding

![Admin bidding](images/user-guide/09-admin-bidding.png)

![Supplier bidding](images/user-guide/10-supplier-bidding.png)

## Approvals and reports

![Pending approvals](images/user-guide/11-pending-approvals.png)

![Invoice aging](images/user-guide/12-invoice-aging.png)

## Tips

- Prefer the role that matches your email directory (customer, admin, or supplier).
- Use hard-refresh (Ctrl+Shift+R) if the UI looks stale after a deploy.
'@ | Set-Content -Path $guideMd -Encoding UTF8
}

if (-not (Test-Path $guideTxt)) {
    Write-Host "Creating docs/USER_GUIDE_FOR_GOOGLE_DOCS.txt ..."
    @'
ProAcc eQuotation User Guide
============================

(Plain-text copy for pasting into Google Docs. Insert screenshots from docs/images/user-guide/ where noted.)

SIGN IN
-------
Screenshot: 01-login.png

1. Open the login page.
2. Choose account type: Customer, Admin / staff, or Supplier.
3. Enter your email and continue to receive a one-time password (OTP).
4. Guests can use Sign in as Guest.

Screenshot: 02-guest-signin.png

ADMIN DASHBOARD
---------------
Screenshot: 03-admin-dashboard.png

After admin login, open the dashboard to reach quotations, procurement, approvals, and reports.

CREATE QUOTATION
----------------
Screenshot: 04-create-quotation.png

Build a sales quotation: pick customer, add lines, review totals, then submit.

MY QUOTATIONS
-------------
Screenshot: 05-my-quotations.png

Customers can review quotations they created.

ADMIN VIEW QUOTATIONS
---------------------
Screenshot: 06-admin-view-quotations.png

Staff can search and open company quotations.

PROCUREMENT
-----------
View purchase requests - Screenshot: 07-procurement-view-pr.png
Create purchase request - Screenshot: 08-procurement-create-pr.png

BIDDING
-------
Admin bidding - Screenshot: 09-admin-bidding.png
Supplier bidding - Screenshot: 10-supplier-bidding.png

APPROVALS AND REPORTS
---------------------
Pending approvals - Screenshot: 11-pending-approvals.png
Invoice aging - Screenshot: 12-invoice-aging.png

TIPS
----
- Prefer the role that matches your email directory (customer, admin, or supplier).
- Use hard-refresh (Ctrl+Shift+R) if the UI looks stale after a deploy.
'@ | Set-Content -Path $guideTxt -Encoding UTF8
}

# --- Ensure app reachable WITH guide capture login ---
$needStart = $true
if (Test-EqReachable $baseUrl) {
    if (Test-GuideCaptureLogin $baseUrl) {
        Write-Host "App reachable with guide capture login at $baseUrl"
        $needStart = $false
    } else {
        Write-Host "App on $Port is up but guide_capture_login missing - restarting with EQ_GUIDE_CAPTURE=1"
        Stop-ListenerOnPort -listenPort $Port
    }
}

if ($needStart) {
    $serverProc = Start-EqGuideServer -listenPort $Port
    $startedServer = $true
    $ok = ($null -ne $serverProc) -and (Test-EqReachable $baseUrl) -and (Test-GuideCaptureLogin $baseUrl)

    if (-not $ok) {
        Write-Host "Primary port $Port failed. Trying fallback ports: $($FallbackPorts -join ', ')"
        foreach ($fp in $FallbackPorts) {
            $tryUrl = "http://127.0.0.1:$fp"
            if ((Test-EqReachable $tryUrl) -and (Test-GuideCaptureLogin $tryUrl)) {
                $Port = $fp
                $baseUrl = $tryUrl
                $ok = $true
                Write-Host "Using fallback app at $baseUrl/login"
                break
            }
        }
    }

    if (-not $ok) {
        Write-Host "ERROR: App did not become reachable with guide capture login"
        if ($serverProc -and -not $serverProc.HasExited) {
            Stop-Process -Id $serverProc.Id -Force -ErrorAction SilentlyContinue
        }
        exit 1
    }
}

# --- Ensure Playwright ---
Write-Host ""
Write-Host "Ensuring Playwright is available..."
& $py -m pip install --quiet playwright
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $py -m playwright install chromium
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

# --- Capture screenshots ---
Write-Host ""
Write-Host "Capturing screenshots against $baseUrl ..."
$env:EQ_GUIDE_BASE_URL = $baseUrl
& $py (Join-Path $PSScriptRoot 'capture_user_guide_screens.py')
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: screenshot capture failed"
    exit $LASTEXITCODE
}

# --- Confirm docs ---
Write-Host ""
if (-not (Test-Path $guideMd)) {
    Write-Host "ERROR: missing $guideMd"
    exit 1
}
if (-not (Test-Path $guideTxt)) {
    Write-Host "ERROR: missing $guideTxt"
    exit 1
}
Write-Host "Confirmed: docs/USER_GUIDE.md"
Write-Host "Confirmed: docs/USER_GUIDE_FOR_GOOGLE_DOCS.txt"

Write-Host ""
Write-Host "PNG files in docs/images/user-guide/:"
Get-ChildItem -Path $imgDir -Filter '*.png' | Sort-Object Name | ForEach-Object {
    Write-Host ("  {0}  ({1} bytes)" -f $_.Name, $_.Length)
}

Write-Host ""
Write-Host "=== Done ==="
if ($startedServer -and $serverProc -and -not $serverProc.HasExited) {
    Write-Host "Note: left a local server process running (PID $($serverProc.Id))."
}

exit 0
