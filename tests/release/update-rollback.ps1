[CmdletBinding()]
param(
    [string]$ApiBaseUrl = "",
    [Parameter(Mandatory = $true)]
    [string]$WorkspaceRoot
)

$ErrorActionPreference = "Stop"
if ([string]::IsNullOrWhiteSpace($ApiBaseUrl)) {
    $endpointPath = Join-Path $env:LOCALAPPDATA "PPTVideoWorkbench\endpoint.json"
    if (-not (Test-Path -LiteralPath $endpointPath -PathType Leaf)) {
        throw "未找到正在运行的 PPT Video Workbench。请先从开始菜单启动程序。"
    }
    $ApiBaseUrl = (Get-Content -LiteralPath $endpointPath -Raw | ConvertFrom-Json).base_url
}
if (-not $ApiBaseUrl.StartsWith("http://127.0.0.1:")) {
    throw "更新回滚脚本只允许连接本机 API"
}

function Invoke-Json {
    param([string]$Path, [string]$Method = "GET", [object]$Body = $null)
    $request = @{ Uri = "$ApiBaseUrl$Path"; Method = $Method }
    if ($null -ne $Body) {
        $request.ContentType = "application/json"
        $request.Body = $Body | ConvertTo-Json -Compress
    }
    return Invoke-RestMethod @request
}

$projectSnapshot = Get-ChildItem -LiteralPath (Join-Path $WorkspaceRoot "projects") -Recurse -File |
    Get-FileHash -Algorithm SHA256
$candidate = Invoke-Json -Path "/api/updates/check"
if ($null -eq $candidate.data) {
    throw "没有可测试的 stable 更新"
}
$staged = Invoke-Json -Path "/api/updates/stage" -Method "POST" -Body @{
    package_relative_path = $candidate.data.package_relative_path
}
if ($staged.data.staged_version -ne $candidate.data.version) {
    throw "更新暂存版本不一致"
}
$applied = Invoke-Json -Path "/api/updates/apply" -Method "POST"
if ($applied.data.status -ne "applied") {
    throw "稳定版更新未成功应用"
}

$rollback = Invoke-Json -Path "/api/updates/rollback" -Method "POST"
if ($rollback.data.status -ne "rolled_back") {
    throw "回滚未完成"
}
$projectAfter = Get-ChildItem -LiteralPath (Join-Path $WorkspaceRoot "projects") -Recurse -File |
    Get-FileHash -Algorithm SHA256
if (($projectSnapshot | ConvertTo-Json) -ne ($projectAfter | ConvertTo-Json)) {
    throw "更新/回滚修改了项目内容"
}
Write-Output "Update rollback smoke passed: stable-only, stage/apply/rollback, project immutability."
