#Requires -RunAsAdministrator
<#
.SYNOPSIS
  One-time (or redeploy) grant: let a Windows user start/stop ProAcc_eQuotation
  without full Administrator rights on later hotfixes.

.PARAMETER ServiceName
  NSSM service name (default ProAcc_eQuotation).

.PARAMETER User
  DOMAIN\user or COMPUTER\user. If empty, reads
  %TEMP%\ProAcc_eQuotation.restart-user.txt then falls back to current user.
#>
param(
    [string]$ServiceName = "ProAcc_eQuotation",
    [string]$User = ""
)

$ErrorActionPreference = "Stop"

function Resolve-RestartUser {
    param([string]$Raw)
    if ($Raw -and $Raw.Trim()) { return $Raw.Trim() }
    $marker = Join-Path $env:TEMP "ProAcc_eQuotation.restart-user.txt"
    if (Test-Path -LiteralPath $marker) {
        $fromFile = (Get-Content -LiteralPath $marker -TotalCount 1 -ErrorAction SilentlyContinue)
        if ($fromFile -and $fromFile.Trim()) { return $fromFile.Trim() }
    }
    if ($env:USERDOMAIN -and $env:USERNAME) {
        return "$($env:USERDOMAIN)\$($env:USERNAME)"
    }
    return $env:USERNAME
}

$account = Resolve-RestartUser -Raw $User
if (-not $account) {
    Write-Error "No user account to grant. Pass -User DOMAIN\user"
}

Write-Host "Granting start/stop on service '$ServiceName' to '$account' ..."

try {
    $sid = ([System.Security.Principal.NTAccount]$account).Translate(
        [System.Security.Principal.SecurityIdentifier]
    ).Value
} catch {
    Write-Error "Cannot resolve SID for '$account': $($_.Exception.Message)"
}

$sdshow = & sc.exe sdshow $ServiceName 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Error "sc sdshow failed for '$ServiceName': $sdshow"
}
$sddl = ($sdshow | Out-String).Trim()
if (-not $sddl) {
    Write-Error "Empty SDDL from sc sdshow $ServiceName"
}

# Query config/status + start/stop + interrogate + read control
$ace = "(A;;CCLCSWRPWPDTLOCRRC;;;$sid)"
if ($sddl -like "*$sid*") {
    Write-Host "SID $sid already present in service ACL — leaving SDDL unchanged."
    Write-Host "OK: $account can already control $ServiceName (or has overlapping rights)."
    exit 0
}

if ($sddl -match '^(?<dacl>.*?)(?<sacl>S:.*)$') {
    $newSddl = $Matches['dacl'] + $ace + $Matches['sacl']
} else {
    $newSddl = $sddl + $ace
}

Write-Host "Applying service ACL..."
& sc.exe sdset $ServiceName $newSddl | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Error "sc sdset failed (exit $LASTEXITCODE). SDDL was: $newSddl"
}

Write-Host "OK: '$account' may start/stop/query '$ServiceName' without full Admin."
Write-Host "Hotfix next time: copy files, then run restart-equotation.cmd (no UAC if grant worked)."
exit 0
