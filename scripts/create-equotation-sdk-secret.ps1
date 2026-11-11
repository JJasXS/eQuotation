# Creates/updates proacc/tenant/{Tenant}/sdkConnections for eQuotation COM SDK login.
# Same JSON shape as SqlAccountSync (companies[] with dcfPath/database/username/password).
param(
    [string]$TenantCode = "TNT10004",
    [string]$Region = "ap-southeast-1",
    [string]$DcfPath = "\\192.168.100.201\Share\SQLACC.DCF",
    [string]$Username = "ADMIN",
    # Must match Dynamo database.dbPath basename for this tenant (edit if different).
    [string]$DatabaseFile = "ACC-ANOZ.FDB",
    [string]$CompanyName = "ANOZ"
)

$ErrorActionPreference = "Stop"
$secretId = "proacc/tenant/$TenantCode/sdkConnections"

Write-Host "Secret: $secretId"
Write-Host "Company: $CompanyName / $DatabaseFile"
Write-Host "DCF: $DcfPath"
Write-Host ""

$secure = Read-Host -AsSecureString "SQL Account password for $Username"
$bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
try {
    $password = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
} finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
}

$payload = @{
    companies = @(
        @{
            name = $CompanyName
            dcfPath = $DcfPath
            database = $DatabaseFile
            username = $Username
            password = $password
        }
    )
} | ConvertTo-Json -Depth 6

$tmp = Join-Path $env:TEMP "sdkConnections-$TenantCode-eq.json"
$env:AWS_PAGER = ""
[System.IO.File]::WriteAllText($tmp, $payload)

aws sts get-caller-identity --region $Region | Out-Host

$exists = $false
$prevEap = $ErrorActionPreference
$ErrorActionPreference = "Continue"
aws secretsmanager describe-secret --secret-id $secretId --region $Region 2>$null | Out-Null
if ($LASTEXITCODE -eq 0) { $exists = $true }
$ErrorActionPreference = $prevEap

if (-not $exists) {
    Write-Host "Creating $secretId ..."
    aws secretsmanager create-secret `
        --name $secretId `
        --description "eQuotation / SqlAccountSync SDK company logins for tenant $TenantCode" `
        --secret-string "file://$tmp" `
        --region $Region `
        --tags Key=tenant,Value=$TenantCode Key=app,Value=eQuotation Key=kind,Value=sdkConnections
    if ($LASTEXITCODE -ne 0) { throw "create-secret failed" }
} else {
    Write-Host "Updating $secretId ..."
    aws secretsmanager put-secret-value `
        --secret-id $secretId `
        --secret-string "file://$tmp" `
        --region $Region
    if ($LASTEXITCODE -ne 0) { throw "put-secret-value failed" }
}

Remove-Item -Force $tmp -ErrorAction SilentlyContinue
Write-Host "Done. Put ADMIN password in Secrets Manager (not .env)."
