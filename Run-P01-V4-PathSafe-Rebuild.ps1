[CmdletBinding()]
param(
    [string]$WorkspaceRoot = "F:\Video",
    [int]$StartupTimeoutSeconds = 40
)

$ErrorActionPreference = "Stop"
$repoRoot = $PSScriptRoot
$prepareRuntime = Join-Path $repoRoot "scripts\prepare-runtime.ps1"
$buildRelease = Join-Path $repoRoot "scripts\build-release.ps1"
$acceptance = Join-Path $repoRoot "tests\release\windows-acceptance.ps1"
$buildTag = "$(Get-Date -Format 'yyyyMMdd-HHmmss')-$([Guid]::NewGuid().ToString('N').Substring(0, 8))"
$buildOutput = "dist/release-v4-$buildTag"
$installerOutputDirectory = Join-Path $repoRoot "release\release-p01-$buildTag"
$artifactManifest = Join-Path $installerOutputDirectory "release-artifacts.json"

foreach ($required in @($prepareRuntime, $buildRelease, $acceptance)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw "Required P01 V4 file is missing: $required"
    }
}

$prepareSource = Get-Content -LiteralPath $prepareRuntime -Raw
foreach ($requiredFragment in @(
    "--config.node-linker=hoisted",
    "--config.inject-workspace-packages=true"
)) {
    if (-not $prepareSource.Contains($requiredFragment)) {
        throw "P01 V4 path-safe runtime patch is missing: $requiredFragment"
    }
}
if ($prepareSource.Contains("deploy --prod --legacy")) {
    throw "Legacy pnpm deployment is still present; P01 V4 will not build an unsafe installer."
}

& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $prepareRuntime
if ($LASTEXITCODE -ne 0) {
    throw "Path-safe runtime preparation failed with exit code $LASTEXITCODE."
}

& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $buildRelease `
    -Output $buildOutput `
    -InstallerOutputDirectory $installerOutputDirectory
if ($LASTEXITCODE -ne 0) {
    throw "Windows installer rebuild failed with exit code $LASTEXITCODE."
}
if (-not (Test-Path -LiteralPath $artifactManifest -PathType Leaf)) {
    throw "Windows installer rebuild did not produce artifact manifest: $artifactManifest"
}

& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $acceptance `
    -ArtifactManifest $artifactManifest `
    -WorkspaceRoot $WorkspaceRoot `
    -StartupTimeoutSeconds $StartupTimeoutSeconds
exit $LASTEXITCODE
