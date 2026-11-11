# Repeatable eQuotation performance harness.
# Usage:
#   powershell -File scripts\perf\run_all.ps1 -Label before
#   powershell -File scripts\perf\run_all.ps1 -Label after
# Optional:
#   -SkipIdle   skip 15/30 minute idle tests
#   -Quick      shorter concurrency (20s) and idle (1/2 min) for smoke only
param(
    [ValidateSet('before','after')]
    [string]$Label = 'before',
    [switch]$SkipIdle,
    [switch]$Quick
)

$ErrorActionPreference = 'Stop'
$Repo = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
if (-not (Test-Path (Join-Path $Repo 'main.py'))) {
    $Repo = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
}
Set-Location $Repo
$Python = Join-Path $Repo '.venv\Scripts\python.exe'
if (-not (Test-Path $Python)) { $Python = 'python' }

$Results = Join-Path $Repo 'perf\results'
New-Item -ItemType Directory -Force -Path $Results | Out-Null

function Stop-Bench {
    $pidFile = Join-Path $Results 'bench.pid'
    if (Test-Path $pidFile) {
        $benchPid = [int](Get-Content $pidFile -ErrorAction SilentlyContinue)
        if ($benchPid -gt 0) {
            try { Stop-Process -Id $benchPid -Force -ErrorAction SilentlyContinue } catch {}
        }
        Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
    }
    # Also kill anything still bound to 8881
    try {
        $conns = Get-NetTCPConnection -LocalPort 8881 -ErrorAction SilentlyContinue |
            Select-Object -ExpandProperty OwningProcess -Unique
        foreach ($p in $conns) {
            if ($p -and $p -ne 0) { Stop-Process -Id $p -Force -ErrorAction SilentlyContinue }
        }
    } catch {}
}

Write-Host "[perf] stopping any previous bench instance..."
Stop-Bench
Start-Sleep -Seconds 1

Write-Host "[perf] starting bench instance on 127.0.0.1:8881..."
$proc = Start-Process -FilePath $Python -ArgumentList @('scripts\perf\run_bench_instance.py') `
    -WorkingDirectory $Repo -PassThru -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $Results "bench_server_$Label.out.log") `
    -RedirectStandardError (Join-Path $Results "bench_server_$Label.err.log")

# Wait for /login
$ready = $false
for ($i = 0; $i -lt 90; $i++) {
    try {
        $r = Invoke-WebRequest -Uri 'http://127.0.0.1:8881/login' -UseBasicParsing -TimeoutSec 3
        if ($r.StatusCode -lt 500) { $ready = $true; break }
    } catch {}
    Start-Sleep -Seconds 1
}
if (-not $ready) {
    Write-Host "[perf] FAIL: bench instance did not become ready"
    Stop-Bench
    exit 2
}
Write-Host "[perf] bench ready (pid=$($proc.Id))"

# Verify guide capture
try {
    $body = '{"role":"admin"}'
    $resp = Invoke-WebRequest -Uri 'http://127.0.0.1:8881/api/guide_capture_login' `
        -Method POST -Body $body -ContentType 'application/json' -UseBasicParsing -TimeoutSec 15
    Write-Host "[perf] guide_capture_login admin => $($resp.StatusCode)"
} catch {
    Write-Host "[perf] WARN guide_capture_login failed: $_"
}

# Pytest
Write-Host "[perf] running pytest..."
& $Python -m pytest tests -q --tb=no 2>&1 | Tee-Object -FilePath (Join-Path $Results "pytest_$Label.txt")
$pytestExit = $LASTEXITCODE
$pytestJson = @{
    status = if ($pytestExit -eq 0) { 'ok' } else { 'failed' }
    exit_code = $pytestExit
    log = "pytest_$Label.txt"
} | ConvertTo-Json -Compress
# Avoid UTF-8 BOM so Python json.loads works without utf-8-sig.
[System.IO.File]::WriteAllText((Join-Path $Results "pytest_$Label.json"), $pytestJson)

# Investigation only on before
if ($Label -eq 'before') {
    & $Python scripts\perf\investigate_code.py
}

$duration = 60
$min15 = 15
$min30 = 30
if ($Quick) {
    $duration = 20
    $min15 = 1
    $min30 = 2
    $env:EQ_PERF_IDLE_MIN_15 = '1'
    $env:EQ_PERF_IDLE_MIN_30 = '2'
}

Write-Host "[perf] page benchmarks..."
& $Python scripts\perf\bench_pages.py --label $Label --repeats 5

Write-Host "[perf] concurrency benchmarks (mixed + api_only)..."
& $Python scripts\perf\bench_concurrency.py --label $Label --duration $duration --levels 1,5,10,20

if (-not $SkipIdle) {
    Write-Host "[perf] idle benchmarks ($min15 / $min30 min)..."
    & $Python scripts\perf\bench_idle.py --label $Label --min15 $min15 --min30 $min30
} else {
    '{"status":"NOT RUN","blocker":"SkipIdle flag set"}' | Set-Content (Join-Path $Results "idle_$Label.json") -Encoding UTF8
}

& $Python scripts\perf\merge_baseline.py --label $Label

if ($Label -eq 'after') {
    Write-Host "[perf] comparing before/after..."
    & $Python scripts\perf\compare.py
}

Write-Host "[perf] stopping bench instance..."
Stop-Bench
Write-Host "[perf] done label=$Label"
exit 0
