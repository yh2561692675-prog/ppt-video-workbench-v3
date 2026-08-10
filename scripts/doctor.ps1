param(
    [string]$BaseUrl = ""
)

$ErrorActionPreference = "Stop"
if ([string]::IsNullOrWhiteSpace($BaseUrl)) {
    $endpointPath = Join-Path $env:LOCALAPPDATA "PPTVideoWorkbench\endpoint.json"
    if (-not (Test-Path -LiteralPath $endpointPath -PathType Leaf)) {
        throw "未找到正在运行的 PPT Video Workbench。请先从开始菜单启动程序。"
    }
    $BaseUrl = (Get-Content -LiteralPath $endpointPath -Raw | ConvertFrom-Json).base_url
}
if (-not $BaseUrl.StartsWith("http://127.0.0.1:") -and -not $BaseUrl.StartsWith("http://localhost:")) {
    throw "doctor.ps1 only permits a local Workbench endpoint"
}

try {
    $report = Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/diagnostics/run"
    $report | ConvertTo-Json -Depth 12
    $package = Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/diagnostics/package"
    Write-Output "P02 diagnostic package: $($package.data.relative_path)"
}
catch {
    $statusCode = 0
    if ($_.Exception.Response -and $_.Exception.Response.StatusCode) {
        $statusCode = [int]$_.Exception.Response.StatusCode
    }
    if ($statusCode -ne 404) {
        throw
    }
    $report = Invoke-RestMethod -Method Get -Uri "$BaseUrl/api/environment"
    $report | ConvertTo-Json -Depth 12
    $package = Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/environment/diagnostic-package"
    Write-Output "Legacy diagnostic package: $($package.data.relative_path)"
}
