# Start bench instance, run idle benchmark, merge baseline, stop.
param(
    [ValidateSet('before','after')]
    [string]$Label = 'before',
    [int]$Min15 = 15,
    [int]$Min30 = 30
)

$ErrorActionPreference = 'Stop'
$Repo = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
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
    try {
        $conns = Get-NetTCPConnection -LocalPort 8881 -ErrorAction SilentlyContinue |
            Select-Object -ExpandProperty OwningProcess -Unique
        foreach ($p in $conns) {
            if ($p -and $p -ne 0) { Stop-Process -Id $p -Force -ErrorAction SilentlyContinue }
        }
    } catch {}
}

Write-Host "[perf] stopping previous bench..."
Stop-Bench
Start-Sleep -Seconds 1

Write-Host "[perf] starting bench on 8881..."
$proc = Start-Process -FilePath $Python -ArgumentList @('scripts\perf\run_bench_instance.py') `
    -WorkingDirectory $Repo -PassThru -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $Results "bench_server_idle_$Label.out.log") `
    -RedirectStandardError (Join-Path $Results "bench_server_idle_$Label.err.log")

$ready = $false
for ($i = 0; $i -lt 90; $i++) {
    try {
        $r = Invoke-WebRequest -Uri 'http://127.0.0.1:8881/login' -UseBasicParsing -TimeoutSec 3
        if ($r.StatusCode -lt 500) { $ready = $true; break }
    } catch {}
    Start-Sleep -Seconds 1
}
if (-not $ready) {
    Write-Host "[perf] FAIL: bench not ready"
    Stop-Bench
    exit 2
}
Write-Host "[perf] bench ready pid=$($proc.Id)"

& $Python scripts\perf\bench_idle.py --label $Label --min15 $Min15 --min30 $Min30
$idleExit = $LASTEXITCODE
& $Python scripts\perf\merge_baseline.py --label $Label
Stop-Bench
Write-Host "[perf] idle exit=$idleExit"
exit $idleExit
