param(
    [string]$Output = "dist/release",
    [string]$InstallerOutputDirectory = "",
    [string]$CandidateId = "",
    [string]$FeaturePolicySource = "",
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
$launcherRoot = Join-Path $stageRoot "launcher"
$pyInstallerDistRoot = Join-Path $stageRoot "_pyinstaller-dist"
$pyInstallerWorkRoot = Join-Path $stageRoot "_pyinstaller-work"
$pyInstallerBundleRoot = Join-Path $pyInstallerDistRoot "workbench"
$pyInstallerLauncherExecutable = Join-Path $pyInstallerDistRoot "workbench-launcher.exe"
$stagePyInstallerBundle = Join-Path $repoRoot "scripts/stage_pyinstaller_onedir.py"
$releaseArtifactsScript = Join-Path $repoRoot "scripts/release_artifacts.py"
$webRoot = Join-Path $stageRoot "web"
$runtimeRoot = Join-Path $stageRoot "runtime"
$runtimeAssetsRoot = Join-Path $repoRoot "runtime-assets"
$featurePolicySourcePath = Join-Path $repoRoot "schemas\feature-policy-default.json"
if (-not [string]::IsNullOrWhiteSpace($FeaturePolicySource)) {
    if ([System.IO.Path]::IsPathRooted($FeaturePolicySource)) {
        $featurePolicySourcePath = $FeaturePolicySource
    }
    else {
        $featurePolicySourcePath = Join-Path $repoRoot $FeaturePolicySource
    }
    $featurePolicySourcePath = [System.IO.Path]::GetFullPath($featurePolicySourcePath)
}
$featurePolicyPath = Join-Path $stageRoot "feature-policy.json"
$licenseRoot = Join-Path $stageRoot "licenses"
$sbomRoot = Join-Path $stageRoot "sbom"
$peripheralBuildScript = Join-Path $repoRoot "peripheral-platform\scripts\build-s0.ps1"
$includePeripheral = $PeripheralEnabled -or ($env:PERIPHERAL_ENABLED -eq "true")
$sourceIntegrityBefore = $null
$sourceIntegrityAfter = $null
$buildSucceeded = $false

function Get-SourceIntegrity {
    $head = (& git -C $repoRoot rev-parse HEAD 2>$null).Trim()
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($head)) {
        throw "Could not read source HEAD."
    }
    $dirty = ((@(& git -C $repoRoot status --porcelain=v1 --untracked-files=all 2>$null)) -join "`n").Trim()
    if ($LASTEXITCODE -ne 0) {
        throw "Could not read source checkout status."
    }
    $lockPath = Join-Path $repoRoot "uv.lock"
    if (-not (Test-Path -LiteralPath $lockPath -PathType Leaf)) {
        throw "uv.lock is required for a frozen release build."
    }
    $lockHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $lockPath).Hash.ToLowerInvariant()
    return [ordered]@{
        head = $head
        dirty = $dirty
        uv_lock_sha256 = $lockHash
    }
}

function Assert-SourceIntegrity {
    param(
        [System.Collections.IDictionary]$Expected,
        [string]$Phase
    )

    $actual = Get-SourceIntegrity
    if (-not [string]::IsNullOrWhiteSpace($actual.dirty)) {
        throw "Source checkout is dirty at release build $Phase."
    }
    if ($actual.head -ne $Expected.head) {
        throw "Source HEAD changed during release build at $Phase."
    }
    if ($actual.uv_lock_sha256 -ne $Expected.uv_lock_sha256) {
        throw "uv.lock changed during release build at $Phase."
    }
    Write-Output ("SOURCE_INTEGRITY_" + $Phase.ToUpperInvariant() + "=" + ($actual | ConvertTo-Json -Compress))
}

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
    $sourceIntegrityBefore = Get-SourceIntegrity
    if (-not [string]::IsNullOrWhiteSpace($sourceIntegrityBefore.dirty)) {
        throw "Source checkout is dirty before release build."
    }
    Write-Output ("SOURCE_INTEGRITY_BEFORE=" + ($sourceIntegrityBefore | ConvertTo-Json -Compress))
    if ($Verify) {
        Assert-RequiredReleaseFile -StageRoot $stageRoot -RelativePath "api\workbench.exe" -Description "API runtime"
        Assert-RequiredReleaseFile -StageRoot $stageRoot -RelativePath "launcher\workbench-launcher.exe" -Description "desktop launcher"
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
        Assert-RequiredReleaseFile -StageRoot $stageRoot -RelativePath "feature-policy.json" -Description "feature policy"
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
    New-Item -ItemType Directory -Path $apiRoot, $launcherRoot, $webRoot, $licenseRoot, $sbomRoot, $installerOutputRoot -Force | Out-Null
    if ([string]::IsNullOrWhiteSpace($CandidateId) -or $CandidateId -notmatch '^rc-[A-Za-z0-9][A-Za-z0-9._-]*$') {
        throw "A valid -CandidateId using the rc- prefix is required for a release build."
    }
    if (-not (Test-Path -LiteralPath $featurePolicySourcePath -PathType Leaf)) {
        throw "Feature policy source was not found: $featurePolicySourcePath"
    }

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

    uv run --frozen --with "pyinstaller==6.16.0" pyinstaller `
        --noconfirm `
        --clean `
        --distpath $pyInstallerDistRoot `
        --workpath $pyInstallerWorkRoot `
        (Join-Path $repoRoot "apps/api/workbench.spec")
    $pyInstallerExitCode = $LASTEXITCODE
    if ($pyInstallerExitCode -ne 0) {
        throw "PyInstaller failed with exit code $pyInstallerExitCode."
    }

    uv run --frozen python $stagePyInstallerBundle `
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

    uv run --frozen --with "pyinstaller==6.16.0" pyinstaller --noconfirm --clean --distpath $pyInstallerDistRoot --workpath (Join-Path $pyInstallerWorkRoot "launcher") (Join-Path $repoRoot "apps/api/workbench-launcher.spec")
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller launcher build failed with exit code $LASTEXITCODE."
    }
    if (-not (Test-Path -LiteralPath $pyInstallerLauncherExecutable -PathType Leaf)) {
        throw "PyInstaller did not produce the desktop launcher: $pyInstallerLauncherExecutable"
    }
    Copy-Item -LiteralPath $pyInstallerLauncherExecutable -Destination $launcherRoot -Force
    Remove-Item -LiteralPath $pyInstallerWorkRoot -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $pyInstallerDistRoot -Recurse -Force -ErrorAction SilentlyContinue

    if (-not (Test-Path -LiteralPath (Join-Path $apiRoot "workbench.exe") -PathType Leaf)) {
        throw "PyInstaller did not produce the API runtime: $(Join-Path $apiRoot 'workbench.exe')"
    }
    Assert-RequiredApiRuntime -StageRoot $stageRoot

    Copy-Item -Path (Join-Path $repoRoot "apps/web/dist/*") -Destination $webRoot -Recurse -Force
    Copy-PreparedRuntime -SourceRoot $runtimeAssetsRoot -DestinationRoot $runtimeRoot
    uv run --frozen python (Join-Path $repoRoot "scripts\build_feature_policy.py") `
        --source $featurePolicySourcePath `
        --output $featurePolicyPath `
        --candidate-id $CandidateId
    if ($LASTEXITCODE -ne 0) {
        throw "Feature policy binding failed with exit code $LASTEXITCODE."
    }
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

    uv run --frozen python scripts/build_runtime_manifest.py `
        --release-root $stageRoot `
        --version "0.1.0" `
        --api-executable (Join-Path $apiRoot "workbench.exe") `
        --web-index (Join-Path $webRoot "index.html") `
        --runtime-root $runtimeRoot `
        --license-notice (Join-Path $licenseRoot "THIRD-PARTY-NOTICES.txt") `
        --sbom (Join-Path $sbomRoot "python-dependencies.json") `
        --feature-policy $featurePolicyPath
    if ($LASTEXITCODE -ne 0) {
        throw "Runtime manifest build failed with exit code $LASTEXITCODE."
    }

    Assert-RequiredReleaseFile -StageRoot $stageRoot -RelativePath "api\workbench.exe" -Description "API runtime"
    Assert-RequiredReleaseFile -StageRoot $stageRoot -RelativePath "launcher\workbench-launcher.exe" -Description "desktop launcher"
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
    Assert-RequiredReleaseFile -StageRoot $stageRoot -RelativePath "feature-policy.json" -Description "feature policy"

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
    $artifactManifestPath = Join-Path $installerOutputRoot "release-artifacts.json"
    uv run --frozen python $releaseArtifactsScript --repository-root $repoRoot --output $artifactManifestPath --installer $installerPath --payload-manifest (Join-Path $stageRoot "runtime-manifest.json") --candidate-id $CandidateId --version "0.1.0"
    if ($LASTEXITCODE -ne 0) {
        throw "Release artifact manifest generation failed with exit code $LASTEXITCODE."
    }
    uv run --frozen python $releaseArtifactsScript --repository-root $repoRoot --verify $artifactManifestPath
    if ($LASTEXITCODE -ne 0) {
        throw "Release artifact manifest verification failed with exit code $LASTEXITCODE."
    }
    Assert-SourceIntegrity -Expected $sourceIntegrityBefore -Phase "after"
    $buildSucceeded = $true
    Write-Output "WINDOWS_RELEASE_BUILD=PASS manifest=$artifactManifestPath"
}
finally {
    if ($null -ne $releasePayloadDrive) {
        & subst $releasePayloadDrive /D | Out-Null
    }
    Pop-Location
    if ($null -ne $sourceIntegrityBefore) {
        try {
            $sourceIntegrityAfter = Get-SourceIntegrity
            Write-Output ("SOURCE_INTEGRITY_FINAL=" + ($sourceIntegrityAfter | ConvertTo-Json -Compress))
            if (
                $sourceIntegrityAfter.head -ne $sourceIntegrityBefore.head -or
                $sourceIntegrityAfter.uv_lock_sha256 -ne $sourceIntegrityBefore.uv_lock_sha256 -or
                -not [string]::IsNullOrWhiteSpace($sourceIntegrityAfter.dirty)
            ) {
                $message = "Source integrity changed during release build."
                if ($buildSucceeded) {
                    throw $message
                }
                Write-Output ("SOURCE_INTEGRITY_MISMATCH=" + $message)
            }
        }
        catch {
            if ($buildSucceeded) {
                throw
            }
            Write-Output ("SOURCE_INTEGRITY_FINAL_ERROR=" + $_.Exception.Message)
        }
    }
}
