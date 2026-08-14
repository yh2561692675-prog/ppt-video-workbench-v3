[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$ArtifactManifest,
    [string]$CandidateManifest = "",
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
$endpointPath = Join-Path $stateRoot "instance.json"
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
    "artifact_resolution", "clean_install", "candidate_identity", "first_launch", "second_launch", "legacy_project",
    "interruption_recovery", "full_preflight", "play_from_start", "final_export",
    "uninstall_reinstall", "reinstall_launch", "version_rollback", "process_cleanup", "workspace_retention"
)
$evidence = [ordered]@{
    schema_version = "2.0"
    release = [ordered]@{
        run_id = $runId
        candidate_id = ""
        artifact_manifest = ""
        candidate_manifest = ""
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
    # Pass the object explicitly: piping an OrderedDictionary through
    # ConvertTo-Json on Windows PowerShell 5.1 serializes only its type name.
    ConvertTo-Json -InputObject ([pscustomobject]$Value) -Depth 12 | Set-Content -LiteralPath $temporary -Encoding UTF8
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
    $phaseEvidence = [ordered]@{
        phase = $Name
        result = $Result
        detail = $Detail
        reason_codes = @($ReasonCodes)
        metrics = $Metrics
    }
    Write-JsonAtomic -Path $detailPath -Value $phaseEvidence
    # Windows PowerShell 5.1/.NET Framework does not expose Path.GetRelativePath.
    # All phase details are created below the report root, so a normalized
    # substring is both portable and fail-closed for unexpected paths.
    $normalizedReport = [System.IO.Path]::GetFullPath($reportPath).TrimEnd([System.IO.Path]::DirectorySeparatorChar, [System.IO.Path]::AltDirectorySeparatorChar)
    $normalizedDetail = [System.IO.Path]::GetFullPath($detailPath)
    if (-not $normalizedDetail.StartsWith($normalizedReport + [System.IO.Path]::DirectorySeparatorChar, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "phase_evidence_escapes_report_root"
    }
    $relative = $normalizedDetail.Substring($normalizedReport.Length + 1).Replace("\", "/")
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
            if ($ownedLauncherPid -le 0 -or $apiPid -le 0) { throw "owned_pid_mismatch" }
            $ownedLauncher = Get-Process -Id $ownedLauncherPid -ErrorAction SilentlyContinue
            if ($null -eq $ownedLauncher) { throw "owned_launcher_missing" }
            $ownedCommand = (Get-CimInstance Win32_Process -Filter "ProcessId=$ownedLauncherPid" -ErrorAction SilentlyContinue).CommandLine
            if ([string]::IsNullOrWhiteSpace($ownedCommand) -or $ownedCommand -notlike "*$InstallRoot*") { throw "owned_pid_mismatch" }
            if (Get-Process -Id $apiPid -ErrorAction SilentlyContinue) { Stop-Process -Id $apiPid -Force -ErrorAction Stop }
            if (-not $ownedLauncher.WaitForExit(10000)) {
                Stop-Process -Id $ownedLauncherPid -Force -ErrorAction Stop
                if (-not $ownedLauncher.WaitForExit(5000)) { throw "owned_launcher_timeout" }
            }
            if ($launcherProcess.Id -ne $ownedLauncherPid -and -not $launcherProcess.HasExited) {
                Stop-Process -Id $launcherProcess.Id -Force -ErrorAction SilentlyContinue
                $launcherProcess.WaitForExit(5000) | Out-Null
            }
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
    # The installer runs the release activation hook before the first launch.
    # Set the isolated roots before invoking it so activation and startup share
    # the same active-release state and diagnostics paths.
    $env:WORKBENCH_WORKSPACE = $WorkspaceRoot
    $env:WORKBENCH_STATE_ROOT = $stateRoot
    $env:WORKBENCH_LOG_ROOT = $diagnosticRoot
    $env:NO_PROXY = "127.0.0.1,localhost,::1"
    & $PythonExecutable (Join-Path $repositoryRoot "scripts\release_artifacts.py") --repository-root $repositoryRoot --verify $ArtifactManifest
    if ($LASTEXITCODE -ne 0) { throw "artifact_manifest_verification_failed" }
    $artifact = Get-Content -LiteralPath $ArtifactManifest -Raw | ConvertFrom-Json
    $candidateId = [string]$artifact.candidate_id
    $candidateRecord = $null
    if (-not [string]::IsNullOrWhiteSpace($CandidateManifest) -and (Test-Path -LiteralPath $CandidateManifest -PathType Leaf)) {
        $candidateRecord = Get-Content -LiteralPath $CandidateManifest -Raw | ConvertFrom-Json
        $evidence.release.candidate_manifest = "candidate:$CandidateManifest"
    }
    else {
        Set-Phase -Name "candidate_identity" -Result "blocked" -ReasonCodes @("candidate_manifest_missing")
    }
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
    if ($null -ne $candidateRecord) {
        $candidateSource = $candidateRecord.source
        $candidatePolicy = $candidateRecord.feature_policy
        $candidateIdentityErrors = @()
        if ([string]$candidateRecord.candidate_id -ne $candidateId) { $candidateIdentityErrors += "candidate_id_mismatch" }
        if ([string]$candidateRecord.status -ne "candidate_frozen") { $candidateIdentityErrors += "candidate_not_frozen" }
        if ($candidateRecord.source.dirty -ne $false) { $candidateIdentityErrors += "source_dirty" }
        if ([string]$candidatePolicy.policy_id -eq "") { $candidateIdentityErrors += "feature_policy_missing" }
        if ($candidateIdentityErrors.Count -eq 0) {
            Set-Phase -Name "candidate_identity" -Result "passed" -ReasonCodes @() -Metrics @{ candidate_id = $candidateId; policy_id = [string]$candidatePolicy.policy_id; source_commit = [string]$candidateSource.git_commit }
        }
        else {
            Set-Phase -Name "candidate_identity" -Result "blocked" -ReasonCodes $candidateIdentityErrors
        }
    }
    Set-Phase -Name "artifact_resolution" -Result "passed" -ReasonCodes @() -Metrics @{ candidate_id = $candidateId; installer_sha256 = $installerSha256 }

    if (Test-Path -LiteralPath $InstallRoot) { throw "install_root_must_be_new:$InstallRoot" }
    New-Item -ItemType Directory -Path $InstallRoot -Force | Out-Null
    Set-Phase -Name "clean_install" -Result "passed" -ReasonCodes @() -Metrics @{ install_root = "isolated" } -Detail "Install root was new and isolated."
    $install = Start-Process -FilePath $installerPath -ArgumentList @("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/DIR=$InstallRoot", "/LOG=$installerLog") -Wait -PassThru -WindowStyle Hidden
    if ($install.ExitCode -ne 0) { throw "installer_exit_code:$($install.ExitCode)" }
    # Inno Setup can return its parent process before the temporary extractor
    # finishes. Wait for the launcher with a bounded timeout before declaring
    # installation success.
    $launcherPath = Join-Path $InstallRoot "launcher\workbench-launcher.exe"
    $installDeadline = (Get-Date).AddSeconds(180)
    while (-not (Test-Path -LiteralPath $launcherPath -PathType Leaf) -and (Get-Date) -lt $installDeadline) {
        Start-Sleep -Milliseconds 500
    }
    if (-not (Test-Path -LiteralPath $launcherPath -PathType Leaf)) { throw "installed_launcher_missing" }
    $installedReleaseRoot = Join-Path $InstallRoot "releases\0.1.0\release"
    $installedPolicyPath = Join-Path $installedReleaseRoot "feature-policy.json"
    $installedRuntimeManifestPath = Join-Path $installedReleaseRoot "runtime-manifest.json"
    if ($null -ne $candidateRecord -and (Test-Path -LiteralPath $installedPolicyPath -PathType Leaf) -and (Test-Path -LiteralPath $installedRuntimeManifestPath -PathType Leaf)) {
        $installedPolicy = Get-Content -LiteralPath $installedPolicyPath -Raw | ConvertFrom-Json
        $installedRuntimeManifest = Get-Content -LiteralPath $installedRuntimeManifestPath -Raw | ConvertFrom-Json
        $installedPolicyHash = (Get-FileHash -LiteralPath $installedPolicyPath -Algorithm SHA256).Hash.ToLowerInvariant()
        $identityErrors = @()
        if ([string]$installedPolicy.candidate_id -ne $candidateId) { $identityErrors += "installed_candidate_id_mismatch" }
        if ([string]$installedPolicy.policy_id -ne [string]$candidateRecord.feature_policy.policy_id) { $identityErrors += "installed_policy_id_mismatch" }
        if ([string]$candidateRecord.feature_policy.sha256 -ne $installedPolicyHash) { $identityErrors += "installed_policy_hash_mismatch" }
        if ([string]$installedRuntimeManifest.feature_policy_sha256 -ne $installedPolicyHash) { $identityErrors += "runtime_policy_hash_mismatch" }
        if ($identityErrors.Count -gt 0) {
            Set-Phase -Name "candidate_identity" -Result "failed" -ReasonCodes $identityErrors
        }
        else {
            $evidence.phases["candidate_identity"].metrics.installed_policy_sha256 = $installedPolicyHash
        }
    }
    else {
        Set-Phase -Name "candidate_identity" -Result "blocked" -ReasonCodes @("installed_identity_files_missing")
    }
    Invoke-Launch -Name "first_launch" -LauncherPath $launcherPath
    Invoke-Launch -Name "second_launch" -LauncherPath $launcherPath
    Set-Phase -Name "legacy_project" -Result "blocked" -ReasonCodes @("operator_sample_required") -Detail "Legacy project path requires an explicit copied sample."
    Set-Phase -Name "interruption_recovery" -Result "blocked" -ReasonCodes @("physical_fault_injection_pending")
    Set-Phase -Name "full_preflight" -Result "blocked" -ReasonCodes @("project_sample_required")
    Set-Phase -Name "play_from_start" -Result "blocked" -ReasonCodes @("project_sample_required")
    Set-Phase -Name "final_export" -Result "blocked" -ReasonCodes @("project_sample_required")

    $uninstaller = Join-Path $InstallRoot "unins000.exe"
    if (Test-Path -LiteralPath $uninstaller -PathType Leaf) {
        $uninstall = Start-Process -FilePath $uninstaller -ArgumentList @("/VERYSILENT", "/NORESTART") -Wait -PassThru -WindowStyle Hidden
        if ($uninstall.ExitCode -eq 0) {
            $removed = -not (Test-Path -LiteralPath $InstallRoot)
            if (-not $removed) {
                Set-Phase -Name "uninstall_reinstall" -Result "failed" -ReasonCodes @("install_root_retained") -Metrics @{ uninstall_exit_code = 0 }
            }
            else {
                $reinstall = Start-Process -FilePath $installerPath -ArgumentList @("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/DIR=$InstallRoot", "/LOG=$installerLog.reinstall") -Wait -PassThru -WindowStyle Hidden
                $reinstalledLauncher = Join-Path $InstallRoot "launcher\workbench-launcher.exe"
                $reinstallDeadline = (Get-Date).AddSeconds(180)
                while (-not (Test-Path -LiteralPath $reinstalledLauncher -PathType Leaf) -and (Get-Date) -lt $reinstallDeadline) { Start-Sleep -Milliseconds 500 }
                if ($reinstall.ExitCode -eq 0 -and (Test-Path -LiteralPath $reinstalledLauncher -PathType Leaf)) {
                    Set-Phase -Name "uninstall_reinstall" -Result "passed" -ReasonCodes @() -Metrics @{ uninstall_exit_code = 0; reinstall_exit_code = $reinstall.ExitCode; install_root_removed = $removed }
                    Invoke-Launch -Name "reinstall_launch" -LauncherPath $reinstalledLauncher
                }
                else {
                    Set-Phase -Name "uninstall_reinstall" -Result "failed" -ReasonCodes @("reinstall_failed") -Metrics @{ uninstall_exit_code = 0; reinstall_exit_code = $reinstall.ExitCode }
                }
            }
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
    $runnerError = $_.Exception.Message
    Set-Content -LiteralPath (Join-Path $diagnosticRoot "runner-error.txt") -Value $runnerError -Encoding UTF8
    if (-not $evidence.phases.Contains("artifact_resolution")) { Set-Phase -Name "artifact_resolution" -Result "failed" -ReasonCodes @("runner_failed") -Detail $_.Exception.Message }
    if (-not $evidence.phases.Contains("clean_install")) { Set-Phase -Name "clean_install" -Result "failed" -ReasonCodes @("runner_failed") -Detail $_.Exception.Message }
    if ($evidence.phases.Contains("clean_install") -and -not $evidence.phases.Contains("first_launch")) { Set-Phase -Name "first_launch" -Result "failed" -ReasonCodes @("runner_failed") -Detail $runnerError }
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
