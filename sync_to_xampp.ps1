param(
    [string]$ProjectRoot = "C:\Users\sd01\eQuotation",
    [string]$XamppPhpRoot = "C:\xampp\htdocs\php",
    [bool]$RestartApache = $false
)

$ErrorActionPreference = 'Stop'

$srcPhp = Join-Path $ProjectRoot 'php'
$dstPhp = $XamppPhpRoot

if (!(Test-Path $srcPhp)) {
    throw "Source PHP folder not found: $srcPhp"
}
if (!(Test-Path $dstPhp)) {
    throw "Destination PHP folder not found: $dstPhp"
}

Write-Host "Syncing PHP files from $srcPhp to $dstPhp ..." -ForegroundColor Cyan

$srcFiles = Get-ChildItem $srcPhp -Filter *.php -File
$srcNames = $srcFiles.Name

foreach ($file in $srcFiles) {
    Copy-Item -Path $file.FullName -Destination (Join-Path $dstPhp $file.Name) -Force
}

# Remove stale PHP files from htdocs/php so both folders stay aligned.
$dstFiles = Get-ChildItem $dstPhp -Filter *.php -File
foreach ($file in $dstFiles) {
    if ($file.Name -notin $srcNames) {
        Remove-Item -Path $file.FullName -Force
        Write-Host "Removed stale file: $($file.Name)" -ForegroundColor DarkYellow
    }
}

Write-Host "Verifying file hashes..." -ForegroundColor Cyan
$mismatches = @()
foreach ($f in $srcFiles) {
    $srcHash = (Get-FileHash -Algorithm SHA256 $f.FullName).Hash
    $dstPath = Join-Path $dstPhp $f.Name

    if (!(Test-Path $dstPath)) {
        $mismatches += "Missing in destination: $($f.Name)"
        continue
    }

    $dstHash = (Get-FileHash -Algorithm SHA256 $dstPath).Hash
    if ($srcHash -ne $dstHash) {
        $mismatches += "Hash mismatch: $($f.Name)"
    }
}

if ($mismatches.Count -gt 0) {
    Write-Host "Sync completed with mismatches:" -ForegroundColor Yellow
    $mismatches | ForEach-Object { Write-Host " - $_" -ForegroundColor Yellow }
    exit 1
}

Write-Host "Sync complete. All files match between project and XAMPP." -ForegroundColor Green

# Optional: Restart Apache after sync
if ($RestartApache) {
    Write-Host "Restarting Apache..." -ForegroundColor Cyan
    $xamppControl = "C:\xampp\xampp_control.exe"
    if (Test-Path $xamppControl) {
        # Stop Apache
        Start-Process -FilePath $xamppControl -ArgumentList "--stopapache" -Wait
        Start-Sleep -Seconds 2
        # Start Apache
        Start-Process -FilePath $xamppControl -ArgumentList "--startapache" -Wait
        Write-Host "Apache restarted successfully." -ForegroundColor Green
    } else {
        Write-Host "XAMPP control utility not found: $xamppControl" -ForegroundColor Red
    }
}
