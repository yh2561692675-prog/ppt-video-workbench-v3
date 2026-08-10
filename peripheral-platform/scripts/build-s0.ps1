[CmdletBinding()]
param(
    [string]$Output = "dist/release",
    [switch]$SkipTests
)

$ErrorActionPreference = "Stop"
$platformRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$repoRoot = Resolve-Path (Join-Path $platformRoot "..")
$releaseRoot = Join-Path $repoRoot $Output
$peripheralRoot = Join-Path $releaseRoot "peripheral"
$buildRoot = Join-Path $repoRoot "dist\peripheral-build"
$venvRoot = Join-Path $buildRoot "venv"
$python = Join-Path $venvRoot "Scripts\python.exe"
$manifestSource = Join-Path $platformRoot "packaging\runtime-manifest.json"
$manifestTarget = Join-Path $peripheralRoot "runtime-manifest.json"

New-Item -ItemType Directory -Path $buildRoot, $releaseRoot -Force | Out-Null
uv venv --python 3.12 --clear $venvRoot
if ($LASTEXITCODE -ne 0) {
    throw "Could not create the isolated S0 build environment."
}
$previousVirtualEnvironment = $env:VIRTUAL_ENV
try {
    $env:VIRTUAL_ENV = $venvRoot
    Push-Location $repoRoot
    try {
        uv sync --frozen --active --all-packages --all-extras --group dev
        if ($LASTEXITCODE -ne 0) {
            throw "Could not install the locked S0 dependencies."
        }
        uv pip install --python $python "pyinstaller==6.16.0"
        if ($LASTEXITCODE -ne 0) {
            throw "Could not install the pinned PyInstaller build tool."
        }
        if (-not $SkipTests) {
            & $python -m pytest peripheral-platform/tests -q
            if ($LASTEXITCODE -ne 0) {
                throw "S0 tests failed; packaging was stopped."
            }
        }
        & $python -m PyInstaller `
            --noconfirm `
            --clean `
            --distpath $releaseRoot `
            --workpath (Join-Path $buildRoot "pyinstaller-work") `
            (Join-Path $platformRoot "packaging\peripheral-host.spec")
        if ($LASTEXITCODE -ne 0) {
            throw "PyInstaller failed to build the S0 peripheral host."
        }
    }
    finally {
        Pop-Location
    }
}
finally {
    $env:VIRTUAL_ENV = $previousVirtualEnvironment
}

Copy-Item -LiteralPath $manifestSource -Destination $manifestTarget -Force
$scriptTarget = Join-Path $peripheralRoot "scripts"
New-Item -ItemType Directory -Path $scriptTarget -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $PSScriptRoot "initialize-s0.ps1") `
    -Destination (Join-Path $scriptTarget "initialize-s0.ps1") -Force

$manifest = Get-Content -LiteralPath $manifestTarget -Raw | ConvertFrom-Json
$hashes = @()
foreach ($relativePath in $manifest.required_files) {
    $candidate = Join-Path $releaseRoot ([string]$relativePath)
    if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) {
        throw "S0 runtime manifest file is missing: $relativePath"
    }
    $hashes += [ordered]@{
        relative_path = ([string]$relativePath).Replace("\", "/")
        sha256 = (Get-FileHash -LiteralPath $candidate -Algorithm SHA256).Hash.ToLowerInvariant()
    }
}
[ordered]@{
    manifest_version = 1
    algorithm = "sha256"
    files = $hashes
} | ConvertTo-Json -Depth 5 | Set-Content `
    -LiteralPath (Join-Path $peripheralRoot "runtime-hashes.json") -Encoding UTF8

Write-Output "S0 peripheral runtime created: $peripheralRoot"
