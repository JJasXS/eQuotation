param(
    [string]$ProjectRoot = "C:\Users\sd01\Chatbot",
    [string]$XamppRoot = "C:\xampp\htdocs"
)

$ErrorActionPreference = 'Stop'

$srcPhp = Join-Path $ProjectRoot 'php'
$dstPhp = Join-Path $XamppRoot 'php'
$srcEnv = Join-Path $ProjectRoot '.env'
$dstEnv = Join-Path $XamppRoot '.env'

if (!(Test-Path $srcPhp)) {
    throw "Source PHP folder not found: $srcPhp"
}
if (!(Test-Path $dstPhp)) {
    throw "Destination PHP folder not found: $dstPhp"
}
if (!(Test-Path $srcEnv)) {
    throw "Source .env file not found: $srcEnv"
}

Write-Host "Syncing PHP files..." -ForegroundColor Cyan
Copy-Item -Path (Join-Path $srcPhp '*.php') -Destination $dstPhp -Force

Write-Host "Syncing .env..." -ForegroundColor Cyan
Copy-Item -Path $srcEnv -Destination $dstEnv -Force

Write-Host "Verifying file hashes..." -ForegroundColor Cyan
$mismatches = @()
$files = Get-ChildItem $srcPhp -Filter *.php -File
foreach ($f in $files) {
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

$envSrcHash = (Get-FileHash -Algorithm SHA256 $srcEnv).Hash
$envDstHash = (Get-FileHash -Algorithm SHA256 $dstEnv).Hash
if ($envSrcHash -ne $envDstHash) {
    $mismatches += 'Hash mismatch: .env'
}

if ($mismatches.Count -gt 0) {
    Write-Host "Sync completed with mismatches:" -ForegroundColor Yellow
    $mismatches | ForEach-Object { Write-Host " - $_" -ForegroundColor Yellow }
    exit 1
}

Write-Host "Sync complete. All files match between project and XAMPP." -ForegroundColor Green
[newline]
# Optional: Restart Apache after sync
param(
    [string]$ProjectRoot = "C:\Users\sd01\Chatbot",
    [string]$XamppRoot = "C:\xampp\htdocs",
    [bool]$RestartApache = $false
)

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
