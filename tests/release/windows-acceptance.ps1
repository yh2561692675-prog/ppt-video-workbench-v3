[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$ArtifactManifest,
    [string]$InstallRoot = "",
    [string]$ReportDirectory = "",
    [string]$WorkspaceRoot = "",
    [string]$PythonExecutable = "",
    [int]$StartupTimeoutSeconds = 40
)

$ErrorActionPreference = "Stop"
$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$runId = [guid]::NewGuid().ToString("N")
if ([string]::IsNullOrWhiteSpace($InstallRoot)) { $InstallRoot = Join-Path $env:TEMP "PPTVideoWorkbench-Personal-$runId\install" }
if ([string]::IsNullOrWhiteSpace($ReportDirectory)) { $ReportDirectory = Join-Path $env:TEMP "PPTVideoWorkbench-Personal-$runId\report" }
if ([string]::IsNullOrWhiteSpace($WorkspaceRoot)) { $WorkspaceRoot = Join-Path $env:TEMP "PPTVideoWorkbench-Personal-$runId\workspace" }
if ([string]::IsNullOrWhiteSpace($PythonExecutable)) { $PythonExecutable = Join-Path $repositoryRoot ".venv\Scripts\python.exe" }
$reportPath = [System.IO.Path]::GetFullPath($ReportDirectory)
$diagnosticRoot = Join-Path $reportPath "diagnostics"
$evidenceRoot = Join-Path $reportPath "phase-evidence"
$stateRoot = Join-Path $reportPath "state"
$endpointPath = Join-Path $stateRoot "endpoint.json"
$retentionMarker = Join-Path $WorkspaceRoot "personal-use-retention.json"
$evidencePath = Join-Path $reportPath "acceptance-evidence.json"
$installerLog = Join-Path $reportPath "installer.log"
$launcherProcess = $null
$candidateId = ""
$installerPath = ""
$installerSha256 = ""
$retentionHash = ""
$previous = @{
    workspace = $env:WORKBENCH_WORKSPACE
    state = $env:WORKBENCH_STATE_ROOT
    log = $env:WORKBENCH_LOG_ROOT
    noProxy = $env:NO_PROXY
}

$requiredPhases = @(
    "artifact_resolution", "clean_install", "first_launch", "legacy_project",
    "interruption_recovery", "full_preflight", "play_from_start", "final_export",
    "uninstall_reinstall", "version_rollback", "process_cleanup", "workspace_retention"
)
$evidence = [ordered]@{
    schema_version = "2.0"
    release = [ordered]@{
        run_id = $runId
        candidate_id = ""
        artifact_manifest = ""
        installer_path = ""
        installer_sha256 = ""
        workspace_root = $WorkspaceRoot
        install_root = $InstallRoot
        execution_mode = "physical_windows"
    }
    phases = [ordered]@{}
}

function Write-JsonAtomic {
    param([Parameter(Mandatory = $true)][string]$Path, [Parameter(Mandatory = $true)]$Value)
    $parent = Split-Path -Parent $Path
    New-Item -ItemType Directory -Path $parent -Force | Out-Null
    $temporary = "$Path.$([guid]::NewGuid().ToString('N')).partial"
    $Value | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $temporary -Encoding UTF8
    Move-Item -LiteralPath $temporary -Destination $Path -Force
}

function Set-Phase {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][ValidateSet("passed", "failed", "blocked", "cancelled")][string]$Result,
        [string[]]$ReasonCodes = @(),
        [hashtable]$Metrics = @{},
        [string]$Detail = ""
    )
    $started = (Get-Date).ToUniversalTime()
    $finished = (Get-Date).ToUniversalTime()
    $detailPath = Join-Path $evidenceRoot "$Name.json"
    $detail = [ordered]@{
        phase = $Name
        result = $Result
        detail = $Detail
        reason_codes = @($ReasonCodes)
        metrics = $Metrics
    }
    Write-JsonAtomic -Path $detailPath -Value $detail
    $relative = [System.IO.Path]::GetRelativePath($reportPath, $detailPath).Replace("\", "/")
    $evidence.phases[$Name] = [ordered]@{
        result = $Result
        started_at = $started.ToString("o")
        finished_at = $finished.ToString("o")
        duration_ms = [int][Math]::Max(0, ($finished - $started).TotalMilliseconds)
        attempt = 1
        reason_codes = @($ReasonCodes)
        evidence_refs = @($relative)
        metrics = $Metrics
    }
}

function Ensure-PhaseDefaults {
    foreach ($name in $requiredPhases) {
        if (-not $evidence.phases.Contains($name)) {
            Set-Phase -Name $name -Result "blocked" -ReasonCodes @("phase_not_executed") -Detail "Phase was not reached by this runner."
        }
    }
}

function Stop-OwnedLauncher {
    param([switch]$BestEffort)
    if ($null -eq $launcherProcess) { return }
    try {
        if (-not $launcherProcess.HasExited) {
            if (-not (Test-Path -LiteralPath $endpointPath -PathType Leaf)) { throw "owned_endpoint_missing" }
            $endpoint = Get-Content -LiteralPath $endpointPath -Raw | ConvertFrom-Json
            $ownedLauncherPid = [int]$endpoint.launcher_pid
            $apiPid = [int]$endpoint.api_pid
            if ($ownedLauncherPid -ne $launcherProcess.Id -or $apiPid -le 0) { throw "owned_pid_mismatch" }
            if (Get-Process -Id $apiPid -ErrorAction SilentlyContinue) { Stop-Process -Id $apiPid -Force -ErrorAction Stop }
            if (-not $launcherProcess.WaitForExit(10000)) { throw "owned_launcher_timeout" }
        }
    }
    catch {
        if ($null -ne $launcherProcess -and -not $launcherProcess.HasExited) {
            Stop-Process -Id $launcherProcess.Id -Force -ErrorAction SilentlyContinue
            $launcherProcess.WaitForExit(10000) | Out-Null
        }
        if (-not $BestEffort) { throw }
    }
    finally { $script:launcherProcess = $null }
}

function Wait-HealthyEndpoint {
    param([int]$TimeoutSeconds)
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-Path -LiteralPath $endpointPath -PathType Leaf) {
            $endpoint = Get-Content -LiteralPath $endpointPath -Raw | ConvertFrom-Json
            $baseUrl = [string]$endpoint.base_url
            if (-not $baseUrl.StartsWith("http://127.0.0.1:")) { throw "non_loopback_endpoint" }
            $health = Invoke-WebRequest -UseBasicParsing -Uri "$baseUrl/api/health" -TimeoutSec 2
            if ($health.StatusCode -eq 200) { return $baseUrl }
        }
        Start-Sleep -Milliseconds 250
    }
    throw "startup_timeout"
}

function Invoke-Launch {
    param([string]$Name, [string]$LauncherPath)
    $stdout = Join-Path $diagnosticRoot "$Name.launcher.stdout.log"
    $stderr = Join-Path $diagnosticRoot "$Name.launcher.stderr.log"
    try {
        if (Test-Path -LiteralPath $endpointPath -PathType Leaf) { throw "existing_endpoint_would_be_interfered_with" }
        $env:WORKBENCH_WORKSPACE = $WorkspaceRoot
        $env:WORKBENCH_STATE_ROOT = $stateRoot
        $env:WORKBENCH_LOG_ROOT = $diagnosticRoot
        $env:NO_PROXY = "127.0.0.1,localhost,::1"
        $script:launcherProcess = Start-Process -FilePath $LauncherPath -ArgumentList @("--app-root", $InstallRoot, "start", "--no-browser") -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru -WindowStyle Hidden
        $baseUrl = Wait-HealthyEndpoint -TimeoutSeconds $StartupTimeoutSeconds
        Stop-OwnedLauncher
        if (Test-Path -LiteralPath $endpointPath -PathType Leaf) { throw "endpoint_not_removed" }
        Set-Phase -Name $Name -Result "passed" -ReasonCodes @() -Metrics @{ base_url = $baseUrl } -Detail "Healthy loopback endpoint and owned shutdown completed."
    }
    catch {
        Set-Phase -Name $Name -Result "failed" -ReasonCodes @("launch_failed") -Metrics @{ stdout = "diagnostics/$Name.launcher.stdout.log"; stderr = "diagnostics/$Name.launcher.stderr.log" } -Detail $_.Exception.Message
        Stop-OwnedLauncher -BestEffort
    }
}

try {
    New-Item -ItemType Directory -Path $reportPath, $diagnosticRoot, $evidenceRoot, $stateRoot, $WorkspaceRoot -Force | Out-Null
    if (-not (Test-Path -LiteralPath $PythonExecutable -PathType Leaf)) { throw "python_executable_missing:$PythonExecutable" }
    if (-not (Test-Path -LiteralPath $ArtifactManifest -PathType Leaf)) { throw "artifact_manifest_missing" }
    & $PythonExecutable (Join-Path $repositoryRoot "scripts\release_artifacts.py") --repository-root $repositoryRoot --verify $ArtifactManifest
    if ($LASTEXITCODE -ne 0) { throw "artifact_manifest_verification_failed" }
    $artifact = Get-Content -LiteralPath $ArtifactManifest -Raw | ConvertFrom-Json
    $candidateId = [string]$artifact.candidate_id
    $relativeInstaller = [string]$artifact.artifacts.installer.relative_path
    if ([string]::IsNullOrWhiteSpace($candidateId) -or [string]::IsNullOrWhiteSpace($relativeInstaller)) { throw "artifact_manifest_identity_missing" }
    $installerPath = [System.IO.Path]::GetFullPath((Join-Path $repositoryRoot $relativeInstaller))
    if (-not $installerPath.StartsWith(([System.IO.Path]::GetFullPath($repositoryRoot) + [System.IO.Path]::DirectorySeparatorChar), [System.StringComparison]::OrdinalIgnoreCase)) { throw "installer_path_escapes_repository" }
    if (-not (Test-Path -LiteralPath $installerPath -PathType Leaf)) { throw "installer_missing" }
    $installerSha256 = (Get-FileHash -LiteralPath $installerPath -Algorithm SHA256).Hash.ToLowerInvariant()
    Copy-Item -LiteralPath $ArtifactManifest -Destination (Join-Path $reportPath "artifact-manifest.json") -Force
    $evidence.release.candidate_id = $candidateId
    $evidence.release.artifact_manifest = "artifact-manifest.json"
    $evidence.release.installer_path = "installer:$relativeInstaller"
    $evidence.release.installer_sha256 = $installerSha256
    Set-Phase -Name "artifact_resolution" -Result "passed" -ReasonCodes @() -Metrics @{ candidate_id = $candidateId; installer_sha256 = $installerSha256 }

    if (Test-Path -LiteralPath $InstallRoot) { throw "install_root_must_be_new:$InstallRoot" }
    New-Item -ItemType Directory -Path $InstallRoot -Force | Out-Null
    Set-Phase -Name "clean_install" -Result "passed" -ReasonCodes @() -Metrics @{ install_root = "isolated" } -Detail "Install root was new and isolated."
    $install = Start-Process -FilePath $installerPath -ArgumentList @("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/DIR=$InstallRoot", "/LOG=$installerLog") -Wait -PassThru -WindowStyle Hidden
    if ($install.ExitCode -ne 0) { throw "installer_exit_code:$($install.ExitCode)" }
    $launcherPath = Join-Path $InstallRoot "launcher\workbench-launcher.exe"
    if (-not (Test-Path -LiteralPath $launcherPath -PathType Leaf)) { throw "installed_launcher_missing" }
    Invoke-Launch -Name "first_launch" -LauncherPath $launcherPath
    Set-Phase -Name "legacy_project" -Result "blocked" -ReasonCodes @("operator_sample_required") -Detail "Legacy project path requires an explicit copied sample."
    Set-Phase -Name "interruption_recovery" -Result "blocked" -ReasonCodes @("physical_fault_injection_pending")
    Set-Phase -Name "full_preflight" -Result "blocked" -ReasonCodes @("project_sample_required")
    Set-Phase -Name "play_from_start" -Result "blocked" -ReasonCodes @("project_sample_required")
    Set-Phase -Name "final_export" -Result "blocked" -ReasonCodes @("project_sample_required")

    $uninstaller = Join-Path $InstallRoot "unins000.exe"
    if (Test-Path -LiteralPath $uninstaller -PathType Leaf) {
        $uninstall = Start-Process -FilePath $uninstaller -ArgumentList @("/VERYSILENT", "/NORESTART") -Wait -PassThru -WindowStyle Hidden
        if ($uninstall.ExitCode -eq 0) {
            Set-Phase -Name "uninstall_reinstall" -Result "passed" -ReasonCodes @() -Metrics @{ uninstall_exit_code = 0 }
        } else {
            Set-Phase -Name "uninstall_reinstall" -Result "failed" -ReasonCodes @("uninstaller_exit_code") -Metrics @{ uninstall_exit_code = $uninstall.ExitCode }
        }
    } else {
        Set-Phase -Name "uninstall_reinstall" -Result "blocked" -ReasonCodes @("uninstaller_missing")
    }
    Set-Phase -Name "version_rollback" -Result "blocked" -ReasonCodes @("previous_candidate_required")
    Stop-OwnedLauncher -BestEffort
    $ownedProcesses = @(Get-CimInstance Win32_Process -Filter "name='workbench-launcher.exe'" -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -like "*$InstallRoot*" })
    if ($ownedProcesses.Count -eq 0) {
        Set-Phase -Name "process_cleanup" -Result "passed" -ReasonCodes @() -Metrics @{ owned_processes = 0 }
    } else {
        Set-Phase -Name "process_cleanup" -Result "failed" -ReasonCodes @("owned_process_remaining") -Metrics @{ owned_processes = $ownedProcesses.Count }
    }
    New-Item -ItemType Directory -Path $WorkspaceRoot -Force | Out-Null
    Set-Content -LiteralPath $retentionMarker -Value "personal-use-retention:$runId" -Encoding UTF8
    $retentionHash = (Get-FileHash -LiteralPath $retentionMarker -Algorithm SHA256).Hash
    if ((Test-Path -LiteralPath $retentionMarker) -and (Get-FileHash -LiteralPath $retentionMarker -Algorithm SHA256).Hash -eq $retentionHash) {
        Set-Phase -Name "workspace_retention" -Result "passed" -ReasonCodes @() -Metrics @{ marker_sha256 = $retentionHash }
    } else {
        Set-Phase -Name "workspace_retention" -Result "failed" -ReasonCodes @("retention_marker_changed")
    }
}
catch {
    if (-not $evidence.phases.Contains("artifact_resolution")) { Set-Phase -Name "artifact_resolution" -Result "failed" -ReasonCodes @("runner_failed") -Detail $_.Exception.Message }
    if (-not $evidence.phases.Contains("clean_install")) { Set-Phase -Name "clean_install" -Result "failed" -ReasonCodes @("runner_failed") -Detail $_.Exception.Message }
}
finally {
    Stop-OwnedLauncher -BestEffort
    Ensure-PhaseDefaults
    Write-JsonAtomic -Path $evidencePath -Value $evidence
    $env:WORKBENCH_WORKSPACE = $previous.workspace
    $env:WORKBENCH_STATE_ROOT = $previous.state
    $env:WORKBENCH_LOG_ROOT = $previous.log
    $env:NO_PROXY = $previous.noProxy
}

& $PythonExecutable (Join-Path $repositoryRoot "scripts\windows_acceptance_report.py") --evidence $evidencePath --output-dir (Join-Path $reportPath "report")
if ($LASTEXITCODE -eq 0) {
    Write-Output "P01_WINDOWS_ACCEPTANCE=PASS"
    exit 0
}
Write-Output "P01_WINDOWS_ACCEPTANCE=BLOCK"
exit 1
