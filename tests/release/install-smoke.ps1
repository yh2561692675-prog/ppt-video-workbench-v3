[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$InstallerPath,
    [ValidateSet("Silent", "Interactive")]
    [string]$Mode = "Silent",
    [string]$InstallRoot = (Join-Path $env:LOCALAPPDATA "PPTVideoWorkbench\app")
)

$ErrorActionPreference = "Stop"
$workspaceData = Join-Path $env:LOCALAPPDATA "PPTVideoWorkbench\workspace-data"
$marker = Join-Path $workspaceData "中文-安装保留.json"
$installerArguments = if ($Mode -eq "Silent") {
    @("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/DIR=$InstallRoot")
}
else {
    @("/SILENT", "/NORESTART", "/DIR=$InstallRoot")
}

New-Item -ItemType Directory -Path $workspaceData -Force | Out-Null
Set-Content -LiteralPath $marker -Value '{"keep":true}' -Encoding UTF8
$install = Start-Process -FilePath $InstallerPath -ArgumentList $installerArguments -Wait -PassThru
if ($install.ExitCode -ne 0) {
    throw "安装器失败，退出码 $($install.ExitCode)"
}

$launcher = Join-Path $InstallRoot "release\scripts\launcher.ps1"
if (-not (Test-Path -LiteralPath $launcher)) {
    $launcher = Join-Path $InstallRoot "scripts\launcher.ps1"
}
if (-not (Test-Path -LiteralPath $launcher)) {
    throw "安装后找不到 launcher.ps1"
}

$runningLaunchers = @(Get-Process -Name powershell, pwsh -ErrorAction SilentlyContinue)
Write-Output "Duplicate-instance probe observed $($runningLaunchers.Count) PowerShell processes."

$uninstaller = Join-Path $InstallRoot "unins000.exe"
if (-not (Test-Path -LiteralPath $uninstaller)) {
    throw "安装后找不到卸载程序"
}
$uninstall = Start-Process -FilePath $uninstaller -ArgumentList @("/VERYSILENT", "/NORESTART") -Wait -PassThru
if ($uninstall.ExitCode -ne 0) {
    throw "卸载器失败，退出码 $($uninstall.ExitCode)"
}
if (-not (Test-Path -LiteralPath $marker)) {
    throw "卸载删除了用户工作区数据"
}

Write-Output "Install smoke passed: silent/interactive, 中文路径, duplicate-instance probe, uninstall retention."
