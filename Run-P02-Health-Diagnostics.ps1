[CmdletBinding()]
param(
    [string]$WorkspaceRoot = "F:\Video",
    [int]$StartupTimeoutSeconds = 60
)

$ErrorActionPreference = "Stop"
$repoRoot = $PSScriptRoot
$prepareRuntime = Join-Path $repoRoot "scripts\prepare-runtime.ps1"
$buildRelease = Join-Path $repoRoot "scripts\build-release.ps1"
$acceptance = Join-Path $repoRoot "tests\release\windows-p02-acceptance.ps1"
$buildTag = "$(Get-Date -Format 'yyyyMMdd-HHmmss')-$([Guid]::NewGuid().ToString('N').Substring(0, 8))"
$buildOutput = "dist/release-p02-$buildTag"
$installerOutputDirectory = Join-Path $repoRoot "release\release-p02-$buildTag"
$installer = Join-Path $installerOutputDirectory "ppt-video-workbench-setup.exe"
$reportDirectory = Join-Path $env:TEMP "PPTVideoWorkbench-P02-Report-$buildTag"

foreach ($required in @($prepareRuntime, $buildRelease, $acceptance)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw "Required P02 file is missing: $required"
    }
}

& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $prepareRuntime
if ($LASTEXITCODE -ne 0) {
    throw "Runtime preparation failed with exit code $LASTEXITCODE."
}

& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $buildRelease `
    -Output $buildOutput `
    -InstallerOutputDirectory $installerOutputDirectory
if ($LASTEXITCODE -ne 0) {
    throw "Windows installer rebuild failed with exit code $LASTEXITCODE."
}
if (-not (Test-Path -LiteralPath $installer -PathType Leaf)) {
    throw "Windows installer rebuild did not produce: $installer"
}

& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $acceptance `
    -InstallerPath $installer `
    -WorkspaceRoot $WorkspaceRoot `
    -ReportDirectory $reportDirectory `
    -StartupTimeoutSeconds $StartupTimeoutSeconds
exit $LASTEXITCODE
