param(
    [string]$Output = "dist/release",
    [string]$InstallerOutputDirectory = "",
    [switch]$Verify,
    [switch]$PeripheralEnabled
)

$ErrorActionPreference = "Stop"
$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$stageRoot = Join-Path $repoRoot $Output
$installerRoot = Join-Path $repoRoot "release"
$installerOutputRoot = $installerRoot
if (-not [string]::IsNullOrWhiteSpace($InstallerOutputDirectory)) {
    if ([System.IO.Path]::IsPathRooted($InstallerOutputDirectory)) {
        $installerOutputRoot = $InstallerOutputDirectory
    }
    else {
        $installerOutputRoot = Join-Path $repoRoot $InstallerOutputDirectory
    }
}
$installerOutputRoot = [System.IO.Path]::GetFullPath($installerOutputRoot)
$apiRoot = Join-Path $stageRoot "api"
$pyInstallerDistRoot = Join-Path $stageRoot "_pyinstaller-dist"
$pyInstallerWorkRoot = Join-Path $stageRoot "_pyinstaller-work"
$pyInstallerBundleRoot = Join-Path $pyInstallerDistRoot "workbench"
$stagePyInstallerBundle = Join-Path $repoRoot "scripts/stage_pyinstaller_onedir.py"
$webRoot = Join-Path $stageRoot "web"
$runtimeRoot = Join-Path $stageRoot "runtime"
$runtimeAssetsRoot = Join-Path $repoRoot "runtime-assets"
$licenseRoot = Join-Path $stageRoot "licenses"
$sbomRoot = Join-Path $stageRoot "sbom"
$peripheralBuildScript = Join-Path $repoRoot "peripheral-platform\scripts\build-s0.ps1"
$includePeripheral = $PeripheralEnabled -or ($env:PERIPHERAL_ENABLED -eq "true")

function Assert-RequiredReleaseFile {
    param(
        [string]$StageRoot,
        [string]$RelativePath,
        [string]$Description
    )

    $requiredPath = Join-Path $StageRoot $RelativePath
    if (-not (Test-Path -LiteralPath $requiredPath -PathType Leaf)) {
        throw "Required release payload was not found ($Description): $requiredPath"
    }
}

function Assert-ExecutableIdentity {
    param(
        [string]$Path,
        [string]$ExpectedName
    )

    $versionOutput = @(& $Path -version 2>&1)
    $exitCode = $LASTEXITCODE
    $firstLine = if ($versionOutput.Count -gt 0) { [string]$versionOutput[0] } else { "" }
    if (
        $exitCode -ne 0 -or
        -not $firstLine.StartsWith("$ExpectedName version", [StringComparison]::OrdinalIgnoreCase)
    ) {
        throw "Runtime executable is not an $ExpectedName executable: $Path"
    }
}

function Assert-QualityFilterCapabilities {
    param(
        [string]$Executable
    )

    $filterOutput = @(& $Executable -hide_banner -filters 2>&1 | Out-String)
    $exitCode = $LASTEXITCODE
    if ($exitCode -ne 0) {
        throw "FFmpeg filter capability probe failed: $Executable"
    }
    $filterText = ($filterOutput -join "`n")
    $requiredFilters = @(
        "blackdetect",
        "freezedetect",
        "ebur128",
        "silencedetect",
        "select",
        "showinfo"
    )
    foreach ($filterName in $requiredFilters) {
        if ($filterText -notmatch "(?im)\s$filterName(\s|$)") {
            throw "FFmpeg runtime is missing required quality filter '$filterName': $Executable"
        }
    }
}

function Assert-RequiredApiRuntime {
    param([string]$StageRoot)

    foreach ($relativePath in @(
        "api\_internal\python312.dll",
        "api\_internal\vcruntime140.dll",
        "api\_internal\vcruntime140_1.dll",
        "api\_internal\msvcp140.dll"
    )) {
        Assert-RequiredReleaseFile -StageRoot $StageRoot -RelativePath $relativePath -Description "API Python runtime dependency"
    }
}

function Copy-PreparedRuntime {
    param(
        [string]$SourceRoot,
        [string]$DestinationRoot
    )

    if (-not (Test-Path -LiteralPath $SourceRoot -PathType Container)) {
        throw "Prepared rendering runtime was not found. Run scripts\\prepare-runtime.ps1 first: $SourceRoot"
    }
    New-Item -ItemType Directory -Path $DestinationRoot -Force | Out-Null
    Copy-Item -Path (Join-Path $SourceRoot "*") -Destination $DestinationRoot -Recurse -Force
}

function Get-FreeSubstDrive {
    for ($code = 90; $code -ge 68; $code--) {
        $driveName = [string][char]$code
        if ($null -eq (Get-PSDrive -Name $driveName -ErrorAction SilentlyContinue)) {
            return "${driveName}:"
        }
    }
    throw "No free drive letter is available for the temporary Inno Setup release mapping."
}

$iscc = Get-Command "ISCC.exe" -ErrorAction SilentlyContinue
if ($null -eq $iscc) {
    $userIsccPath = Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe"
    if (Test-Path -LiteralPath $userIsccPath -PathType Leaf) {
        $isccPath = $userIsccPath
    }
    else {
        throw "Inno Setup 6 compiler (ISCC.exe) was not found."
    }
}
else {
    $isccPath = [string]$iscc.Source
    if ([string]::IsNullOrWhiteSpace($isccPath)) {
        $isccPath = [string]$iscc.Path
    }
}

Push-Location $repoRoot
$releasePayloadDrive = $null
try {
    if ($Verify) {
        Assert-RequiredReleaseFile -StageRoot $stageRoot -RelativePath "api\workbench.exe" -Description "API runtime"
        Assert-RequiredApiRuntime -StageRoot $stageRoot
        Assert-RequiredReleaseFile -StageRoot $stageRoot -RelativePath "web\index.html" -Description "Web entry"
        Assert-RequiredReleaseFile -StageRoot $stageRoot -RelativePath "runtime\node\node.exe" -Description "Node runtime"
        Assert-RequiredReleaseFile -StageRoot $stageRoot -RelativePath "runtime\ffmpeg\ffmpeg.exe" -Description "FFmpeg runtime"
        Assert-RequiredReleaseFile -StageRoot $stageRoot -RelativePath "runtime\ffmpeg\ffprobe.exe" -Description "FFprobe runtime"
        Assert-ExecutableIdentity -Path (Join-Path $stageRoot "runtime\ffmpeg\ffmpeg.exe") -ExpectedName "ffmpeg"
        Assert-ExecutableIdentity -Path (Join-Path $stageRoot "runtime\ffmpeg\ffprobe.exe") -ExpectedName "ffprobe"
        Assert-QualityFilterCapabilities -Executable (Join-Path $stageRoot "runtime\ffmpeg\ffmpeg.exe")
        Assert-RequiredReleaseFile -StageRoot $stageRoot -RelativePath "runtime\remotion\node_modules\@remotion\cli\remotion-cli.js" -Description "Remotion CLI"
        Assert-RequiredReleaseFile -StageRoot $stageRoot -RelativePath "runtime\remotion\src\index.ts" -Description "Remotion entry"
        Assert-RequiredReleaseFile -StageRoot $stageRoot -RelativePath "runtime-manifest.json" -Description "runtime manifest"
        if ($includePeripheral) {
            Assert-RequiredReleaseFile -StageRoot $stageRoot -RelativePath "peripheral\peripheral-host.exe" -Description "peripheral host"
            Assert-RequiredReleaseFile -StageRoot $stageRoot -RelativePath "peripheral\runtime-manifest.json" -Description "peripheral runtime manifest"
            Assert-RequiredReleaseFile -StageRoot $stageRoot -RelativePath "peripheral\runtime-hashes.json" -Description "peripheral runtime hashes"
        }
        Write-Output "Release staging payload verification passed: $stageRoot"
        exit 0
    }

    if (Test-Path -LiteralPath $stageRoot) {
        Remove-Item -LiteralPath $stageRoot -Recurse -Force
    }
    New-Item -ItemType Directory -Path $apiRoot, $webRoot, $licenseRoot, $sbomRoot, $installerOutputRoot -Force | Out-Null

    if ($includePeripheral) {
        if (-not (Test-Path -LiteralPath $peripheralBuildScript -PathType Leaf)) {
            throw "PeripheralEnabled requires build-s0.ps1."
        }
        & $peripheralBuildScript -Output $Output
        if ($LASTEXITCODE -ne 0) {
            throw "PeripheralEnabled build failed."
        }
        Assert-RequiredReleaseFile -StageRoot $stageRoot -RelativePath "peripheral\peripheral-host.exe" -Description "peripheral host"
        Assert-RequiredReleaseFile -StageRoot $stageRoot -RelativePath "peripheral\runtime-manifest.json" -Description "peripheral runtime manifest"
        Assert-RequiredReleaseFile -StageRoot $stageRoot -RelativePath "peripheral\runtime-hashes.json" -Description "peripheral runtime hashes"
    }

    uv sync --frozen
    if ($LASTEXITCODE -ne 0) {
        throw "uv sync failed with exit code $LASTEXITCODE."
    }
    pnpm install --frozen-lockfile
    if ($LASTEXITCODE -ne 0) {
        throw "pnpm install failed with exit code $LASTEXITCODE."
    }
    pnpm check
    if ($LASTEXITCODE -ne 0) {
        throw "pnpm check failed with exit code $LASTEXITCODE."
    }
    pnpm --filter remotion build
    if ($LASTEXITCODE -ne 0) {
        throw "Remotion build failed with exit code $LASTEXITCODE."
    }

    uv run --with "pyinstaller==6.16.0" pyinstaller `
        --noconfirm `
        --clean `
        --distpath $pyInstallerDistRoot `
        --workpath $pyInstallerWorkRoot `
        (Join-Path $repoRoot "apps/api/workbench.spec")
    $pyInstallerExitCode = $LASTEXITCODE
    if ($pyInstallerExitCode -ne 0) {
        throw "PyInstaller failed with exit code $pyInstallerExitCode."
    }

    uv run python $stagePyInstallerBundle `
        --source $pyInstallerBundleRoot `
        --destination $apiRoot
    $stagePyInstallerExitCode = $LASTEXITCODE
    if ($stagePyInstallerExitCode -ne 0) {
        throw "PyInstaller onedir staging failed with exit code $stagePyInstallerExitCode."
    }
    foreach ($temporaryPath in @($pyInstallerWorkRoot, $pyInstallerDistRoot)) {
        if (Test-Path -LiteralPath $temporaryPath) {
            Remove-Item -LiteralPath $temporaryPath -Recurse -Force
        }
    }

    if (-not (Test-Path -LiteralPath (Join-Path $apiRoot "workbench.exe") -PathType Leaf)) {
        throw "PyInstaller did not produce the API runtime: $(Join-Path $apiRoot 'workbench.exe')"
    }
    Assert-RequiredApiRuntime -StageRoot $stageRoot

    Copy-Item -Path (Join-Path $repoRoot "apps/web/dist/*") -Destination $webRoot -Recurse -Force
    Copy-PreparedRuntime -SourceRoot $runtimeAssetsRoot -DestinationRoot $runtimeRoot
    $pythonDependencies = @(uv pip list --format json)
    if ($LASTEXITCODE -ne 0) {
        throw "Python dependency inventory failed with exit code $LASTEXITCODE."
    }
    $pythonDependencies | Set-Content -LiteralPath (Join-Path $sbomRoot "python-dependencies.json") -Encoding UTF8
    $nodeDependencies = @(pnpm list --prod --depth -1 --json)
    if ($LASTEXITCODE -ne 0) {
        throw "Node dependency inventory failed with exit code $LASTEXITCODE."
    }
    $nodeDependencies | Set-Content -LiteralPath (Join-Path $sbomRoot "node-dependencies.json") -Encoding UTF8
    @(
        "PPT Video Workbench third-party dependency inventory",
        "",
        "Python dependency inventory: sbom/python-dependencies.json",
        "Node dependency inventory: sbom/node-dependencies.json"
    ) | Set-Content -LiteralPath (Join-Path $licenseRoot "THIRD-PARTY-NOTICES.txt") -Encoding UTF8

    uv run python scripts/build_runtime_manifest.py `
        --release-root $stageRoot `
        --version "0.1.0" `
        --api-executable (Join-Path $apiRoot "workbench.exe") `
        --web-index (Join-Path $webRoot "index.html") `
        --runtime-root $runtimeRoot `
        --license-notice (Join-Path $licenseRoot "THIRD-PARTY-NOTICES.txt") `
        --sbom (Join-Path $sbomRoot "python-dependencies.json")
    if ($LASTEXITCODE -ne 0) {
        throw "Runtime manifest build failed with exit code $LASTEXITCODE."
    }

    Assert-RequiredReleaseFile -StageRoot $stageRoot -RelativePath "api\workbench.exe" -Description "API runtime"
    Assert-RequiredReleaseFile -StageRoot $stageRoot -RelativePath "web\index.html" -Description "Web entry"
    Assert-RequiredReleaseFile -StageRoot $stageRoot -RelativePath "runtime\node\node.exe" -Description "Node runtime"
    Assert-RequiredReleaseFile -StageRoot $stageRoot -RelativePath "runtime\ffmpeg\ffmpeg.exe" -Description "FFmpeg runtime"
    Assert-RequiredReleaseFile -StageRoot $stageRoot -RelativePath "runtime\ffmpeg\ffprobe.exe" -Description "FFprobe runtime"
    Assert-ExecutableIdentity -Path (Join-Path $stageRoot "runtime\ffmpeg\ffmpeg.exe") -ExpectedName "ffmpeg"
    Assert-ExecutableIdentity -Path (Join-Path $stageRoot "runtime\ffmpeg\ffprobe.exe") -ExpectedName "ffprobe"
    Assert-QualityFilterCapabilities -Executable (Join-Path $stageRoot "runtime\ffmpeg\ffmpeg.exe")
    Assert-RequiredReleaseFile -StageRoot $stageRoot -RelativePath "runtime\remotion\node_modules\@remotion\cli\remotion-cli.js" -Description "Remotion CLI"
    Assert-RequiredReleaseFile -StageRoot $stageRoot -RelativePath "runtime\remotion\src\index.ts" -Description "Remotion entry"
    Assert-RequiredReleaseFile -StageRoot $stageRoot -RelativePath "runtime-manifest.json" -Description "runtime manifest"

    $releasePayloadDrive = Get-FreeSubstDrive
    & subst $releasePayloadDrive $stageRoot
    if ($LASTEXITCODE -ne 0) {
        throw "Could not create the temporary Inno Setup release mapping: $releasePayloadDrive"
    }

    & $isccPath "/DReleasePayload=$releasePayloadDrive" "/O$installerOutputRoot" "/Fppt-video-workbench-setup" (Join-Path $repoRoot "installer/workbench.iss")
    $isccExitCode = $LASTEXITCODE
    if ($isccExitCode -ne 0) {
        throw "Inno Setup compiler failed with exit code $isccExitCode. Installer was not created: $installerOutputRoot"
    }
    $installerPath = Join-Path $installerOutputRoot "ppt-video-workbench-setup.exe"
    if (-not (Test-Path -LiteralPath $installerPath -PathType Leaf)) {
        throw "Inno Setup did not create the installer: $installerPath"
    }
    Write-Output "Windows installer created: $installerPath"
}
finally {
    if ($null -ne $releasePayloadDrive) {
        & subst $releasePayloadDrive /D | Out-Null
    }
    Pop-Location
}
