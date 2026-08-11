[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$ArtifactManifest,
    [string]$InstallRoot = (Join-Path $env:TEMP "PPTVideoWorkbench-P01"),
    [string]$ReportDirectory = (Join-Path $env:TEMP "PPTVideoWorkbench-P01-Report"),
    [string]$WorkspaceRoot = "F:\Video",
    [int]$StartupTimeoutSeconds = 40
)

$ErrorActionPreference = "Stop"
$repositoryRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$artifactScript = Join-Path $repositoryRoot "scripts\release_artifacts.py"
$stateRoot = Join-Path $env:TEMP ("PPTVideoWorkbench-P01-State-" + [guid]::NewGuid().ToString("N"))
$diagnosticRoot = Join-Path $ReportDirectory "launch-diagnostics"
$endpointPath = Join-Path $stateRoot "endpoint.json"
$workspaceDataRoot = Join-Path $stateRoot "workspace-data"
$retentionMarker = Join-Path $workspaceDataRoot "p01-retention.json"
$evidencePath = Join-Path $ReportDirectory "acceptance-evidence.json"
$installerLog = Join-Path $ReportDirectory "installer.log"
$launcherProcess = $null
$previousWorkspace = $env:WORKBENCH_WORKSPACE
$previousStateRoot = $env:WORKBENCH_STATE_ROOT
$previousLogRoot = $env:WORKBENCH_LOG_ROOT

$evidence = [ordered]@{
    schema_version = "1.0"
    release = [ordered]@{
        artifact_manifest = $ArtifactManifest
        candidate_id = ""
        installer_path = ""
        installer_sha256 = ""
        installer_log = $installerLog
    }
    phases = [ordered]@{}
}

function Set-PhaseResult {
    param(
        [string]$Name,
        [string]$Result,
        [string]$Detail = ""
    )

    $evidence.phases[$Name] = [ordered]@{
        result = $Result
        detail = $Detail
    }
}

function Stop-LauncherProcess {
    param([switch]$BestEffort)

    if ($null -eq $launcherProcess) {
        return
    }
    try {
        if (-not $launcherProcess.HasExited) {
            if (-not (Test-Path -LiteralPath $endpointPath -PathType Leaf)) {
                throw "Owned launcher endpoint record was not found during shutdown."
            }
            $endpoint = Get-Content -LiteralPath $endpointPath -Raw | ConvertFrom-Json
            $ownedLauncherPid = [int]$endpoint.launcher_pid
            $apiPid = [int]$endpoint.api_pid
            if ($ownedLauncherPid -ne $launcherProcess.Id) {
                throw "Endpoint launcher PID does not match the owned launcher."
            }
            if ($apiPid -le 0) {
                throw "Endpoint did not provide a valid owned API PID."
            }
            if (Get-Process -Id $apiPid -ErrorAction SilentlyContinue) {
                Stop-Process -Id $apiPid -Force -ErrorAction Stop
            }
            if (-not $launcherProcess.WaitForExit(10000)) {
                throw "Owned launcher did not exit after its API process stopped."
            }
        }
    }
    catch {
        if (-not $launcherProcess.HasExited) {
            Stop-Process -Id $launcherProcess.Id -Force -ErrorAction SilentlyContinue
            $launcherProcess.WaitForExit(10000) | Out-Null
        }
        if (-not $BestEffort) {
            throw
        }
    }
    finally {
        $script:launcherProcess = $null
    }
}

function Wait-ForEndpoint {
    param([int]$TimeoutSeconds)

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-Path -LiteralPath $endpointPath -PathType Leaf) {
            $endpoint = Get-Content -LiteralPath $endpointPath -Raw | ConvertFrom-Json
            $baseUrl = [string]$endpoint.base_url
            if (-not $baseUrl.StartsWith("http://127.0.0.1:")) {
                throw "Installed launcher returned a non-loopback endpoint."
            }
            $health = Invoke-WebRequest -UseBasicParsing -Uri "$baseUrl/api/health" -TimeoutSec 2
            if ($health.StatusCode -eq 200) {
                return $baseUrl
            }
        }
        Start-Sleep -Milliseconds 250
    }
    throw "Installed application did not become healthy within $TimeoutSeconds seconds."
}

function Wait-ForEndpointRemoval {
    param([int]$TimeoutSeconds)

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if (-not (Test-Path -LiteralPath $endpointPath -PathType Leaf)) {
            return
        }
        Start-Sleep -Milliseconds 250
    }
    throw "Owned launcher did not remove its endpoint record."
}

function Invoke-LaunchPhase {
    param([string]$Name, [string]$LauncherPath)

    $launcherStdout = Join-Path $diagnosticRoot ("$Name.launcher.stdout.log")
    $launcherStderr = Join-Path $diagnosticRoot ("$Name.launcher.stderr.log")
    try {
        New-Item -ItemType Directory -Path $diagnosticRoot -Force | Out-Null
        if (Test-Path -LiteralPath $endpointPath -PathType Leaf) {
            throw "An existing PPT Video Workbench endpoint is active; P01 will not interfere with it."
        }
        $env:WORKBENCH_WORKSPACE = $workspaceDataRoot
        $env:WORKBENCH_STATE_ROOT = $stateRoot
        $env:WORKBENCH_LOG_ROOT = $diagnosticRoot
        $script:launcherProcess = Start-Process `
            -FilePath $LauncherPath `
            -ArgumentList @(
                "--app-root",
                $InstallRoot,
                "start",
                "--no-browser"
            ) `
            -RedirectStandardOutput $launcherStdout `
            -RedirectStandardError $launcherStderr `
            -PassThru `
            -WindowStyle Hidden
        $baseUrl = Wait-ForEndpoint -TimeoutSeconds $StartupTimeoutSeconds
        Set-PhaseResult -Name $Name -Result "passed" -Detail "Healthy loopback endpoint: $baseUrl"
        Stop-LauncherProcess
        Wait-ForEndpointRemoval -TimeoutSeconds 10
        return $true
    }
    catch {
        $detail = "{0} Diagnostics: launcher_stdout={1}; launcher_stderr={2}; root={3}" -f `
            $_.Exception.Message, $launcherStdout, $launcherStderr, $diagnosticRoot
        Set-PhaseResult -Name $Name -Result "failed" -Detail $detail
        Stop-LauncherProcess -BestEffort
        return $false
    }
}

try {
    New-Item -ItemType Directory -Path $ReportDirectory, $workspaceDataRoot -Force | Out-Null
    if (-not (Test-Path -LiteralPath $ArtifactManifest -PathType Leaf)) {
        throw "Release artifact manifest was not found: $ArtifactManifest"
    }
    & uv run python $artifactScript --repository-root $repositoryRoot --verify $ArtifactManifest
    if ($LASTEXITCODE -ne 0) {
        throw "Release artifact manifest verification failed: $ArtifactManifest"
    }
    $artifact = Get-Content -LiteralPath $ArtifactManifest -Raw | ConvertFrom-Json
    $candidateId = [string]$artifact.candidate_id
    $installerRelativePath = [string]$artifact.artifacts.installer.relative_path
    if ([string]::IsNullOrWhiteSpace($candidateId) -or [string]::IsNullOrWhiteSpace($installerRelativePath)) {
        throw "Release artifact manifest is missing candidate_id or installer relative path."
    }
    $installerCandidate = [System.IO.Path]::GetFullPath((Join-Path $repositoryRoot $installerRelativePath))
    $repositoryCandidateRoot = [System.IO.Path]::GetFullPath($repositoryRoot)
    if (-not $installerCandidate.StartsWith($repositoryCandidateRoot + [System.IO.Path]::DirectorySeparatorChar, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Release artifact installer path escapes repository root."
    }
    $InstallerPath = $installerCandidate
    $evidence.release.candidate_id = $candidateId
    $evidence.release.installer_path = $InstallerPath
    Set-PhaseResult -Name "artifact_resolution" -Result "passed" -Detail "Verified candidate $candidateId."
    if (-not (Test-Path -LiteralPath $InstallerPath -PathType Leaf)) {
        throw "Installer was not found: $InstallerPath"
    }
    $evidence.release.installer_sha256 = (Get-FileHash -LiteralPath $InstallerPath -Algorithm SHA256).Hash
    Set-Content -LiteralPath $retentionMarker -Value '{"keep":true}' -Encoding UTF8
    $retentionHash = (Get-FileHash -LiteralPath $retentionMarker -Algorithm SHA256).Hash

    try {
        $install = Start-Process `
            -FilePath $InstallerPath `
            -ArgumentList @(
                "/VERYSILENT",
                "/SUPPRESSMSGBOXES",
                "/NORESTART",
                "/DIR=$InstallRoot",
                "/LOG=$installerLog"
            ) `
            -Wait `
            -PassThru
        if ($install.ExitCode -ne 0) {
            throw "Installer exited with code $($install.ExitCode). Installer log: $installerLog"
        }
        Set-PhaseResult -Name "install" -Result "passed" -Detail "Installer completed."
    }
    catch {
        Set-PhaseResult -Name "install" -Result "failed" -Detail $_.Exception.Message
    }

    $launcherPath = Join-Path $InstallRoot "launcher\workbench-launcher.exe"
    if ($evidence.phases.install.result -eq "passed" -and -not (Test-Path -LiteralPath $launcherPath -PathType Leaf)) {
        Set-PhaseResult -Name "install" -Result "failed" -Detail "Installed GUI launcher was not found."
    }
    if ($evidence.phases.install.result -eq "passed") {
        try {
            $installedVersions = @(Get-ChildItem -LiteralPath (Join-Path $InstallRoot "releases") -Directory)
            if ($installedVersions.Count -ne 1) {
                throw "Expected exactly one installed release slot."
            }
            $installedVersion = $installedVersions[0].Name
            $installedRelease = Join-Path $installedVersions[0].FullName "release"
            $activation = Start-Process `
                -FilePath $launcherPath `
                -ArgumentList @(
                    "--app-root", $InstallRoot, "activate", "--version", $installedVersion,
                    "--release-root", $installedRelease
                ) `
                -Wait `
                -PassThru `
                -WindowStyle Hidden
            if ($activation.ExitCode -ne 0) {
                throw "Installed launcher could not activate the release slot."
            }
        }
        catch {
            Set-PhaseResult -Name "install" -Result "failed" -Detail $_.Exception.Message
        }
    }

    if ($evidence.phases.install.result -eq "passed") {
        $firstLaunchPassed = Invoke-LaunchPhase -Name "first_launch" -LauncherPath $launcherPath
        if ($firstLaunchPassed) {
            Invoke-LaunchPhase -Name "restart" -LauncherPath $launcherPath | Out-Null
        }
    }

    if ($evidence.phases.install.result -eq "passed") {
        try {
            $uninstaller = Join-Path $InstallRoot "unins000.exe"
            if (-not (Test-Path -LiteralPath $uninstaller -PathType Leaf)) {
                throw "Installed uninstaller was not found."
            }
            $uninstall = Start-Process `
                -FilePath $uninstaller `
                -ArgumentList @("/VERYSILENT", "/NORESTART") `
                -Wait `
                -PassThru
            if ($uninstall.ExitCode -ne 0) {
                throw "Uninstaller exited with code $($uninstall.ExitCode)."
            }
            Set-PhaseResult -Name "uninstall" -Result "passed" -Detail "Uninstaller completed."
        }
        catch {
            Set-PhaseResult -Name "uninstall" -Result "failed" -Detail $_.Exception.Message
        }
    }

    try {
        if (-not (Test-Path -LiteralPath $retentionMarker -PathType Leaf)) {
            throw "Uninstall removed the workspace retention marker."
        }
        $retainedHash = (Get-FileHash -LiteralPath $retentionMarker -Algorithm SHA256).Hash
        if ($retainedHash -ne $retentionHash) {
            throw "Uninstall modified the workspace retention marker."
        }
        Set-PhaseResult -Name "workspace_retention" -Result "passed" -Detail "Workspace marker hash retained."
    }
    catch {
        Set-PhaseResult -Name "workspace_retention" -Result "failed" -Detail $_.Exception.Message
    }
}
catch {
    if (-not $evidence.phases.Contains("artifact_resolution")) {
        Set-PhaseResult -Name "artifact_resolution" -Result "failed" -Detail $_.Exception.Message
    }
    Set-PhaseResult -Name "install" -Result "failed" -Detail $_.Exception.Message
}
finally {
    Stop-LauncherProcess -BestEffort
    $env:WORKBENCH_WORKSPACE = $previousWorkspace
    $env:WORKBENCH_STATE_ROOT = $previousStateRoot
    $env:WORKBENCH_LOG_ROOT = $previousLogRoot
    $evidence | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $evidencePath -Encoding UTF8
}

& uv run python (Join-Path $repositoryRoot "scripts\windows_acceptance_report.py") `
    --evidence $evidencePath `
    --output-dir $ReportDirectory
$reportExitCode = $LASTEXITCODE
if ($reportExitCode -eq 0) {
    Write-Output "P01_WINDOWS_ACCEPTANCE=PASS"
    exit 0
}

Write-Output "P01_WINDOWS_ACCEPTANCE=BLOCK"
exit 1
