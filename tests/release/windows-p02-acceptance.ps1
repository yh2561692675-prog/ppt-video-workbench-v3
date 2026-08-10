[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$InstallerPath,
    [string]$WorkspaceRoot = "F:\Video",
    [string]$InstallRoot = (Join-Path $env:TEMP ("PPTVideoWorkbench-P02-" + [Guid]::NewGuid().ToString("N"))),
    [string]$ReportDirectory = (Join-Path $env:TEMP "PPTVideoWorkbench-P02-Report"),
    [int]$StartupTimeoutSeconds = 60
)

$ErrorActionPreference = "Stop"
$stateRoot = Join-Path $env:TEMP ("PPTVideoWorkbench-P02-State-" + [Guid]::NewGuid().ToString("N"))
$acceptanceWorkspace = Join-Path $stateRoot "workspace"
$logRoot = Join-Path $stateRoot "logs"
$endpointPath = Join-Path $stateRoot "endpoint.json"
$installerLog = Join-Path $ReportDirectory "installer.log"
$evidencePath = Join-Path $ReportDirectory "p02-acceptance.json"
$launcherProcess = $null
$installed = $false
$passed = $false
$failure = ""
$packagePath = ""
$previousWorkspace = $env:WORKBENCH_WORKSPACE
$previousDiagnosticRoot = $env:WORKBENCH_DIAGNOSTIC_ROOT
$previousStateRoot = $env:WORKBENCH_STATE_ROOT
$previousLogRoot = $env:WORKBENCH_LOG_ROOT

$expectedCheckIds = @(
    "installation_manifest",
    "python_runtime",
    "ffmpeg_runtime",
    "disk_space",
    "workspace_permissions",
    "loopback_port",
    "database_integrity",
    "configuration",
    "heygen_connectivity",
    "heygen_voices",
    "secret_references",
    "temporary_directory",
    "video_encoder"
)

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
            try {
                $health = Invoke-WebRequest -UseBasicParsing -Uri "$baseUrl/api/health" -TimeoutSec 2
                if ($health.StatusCode -eq 200) {
                    return $baseUrl
                }
            }
            catch {
                Start-Sleep -Milliseconds 250
            }
        }
        elseif ($launcherProcess -and $launcherProcess.HasExited) {
            throw "Installed launcher exited before publishing a healthy endpoint."
        }
        else {
            Start-Sleep -Milliseconds 250
        }
    }
    throw "Installed application did not become healthy within $TimeoutSeconds seconds."
}

function Stop-OwnedLauncher {
    param([switch]$BestEffort)

    if ($null -eq $launcherProcess) {
        return
    }
    try {
        if (-not $launcherProcess.HasExited) {
            if (-not (Test-Path -LiteralPath $endpointPath -PathType Leaf)) {
                throw "Owned launcher endpoint record is missing."
            }
            $endpoint = Get-Content -LiteralPath $endpointPath -Raw | ConvertFrom-Json
            if ([int]$endpoint.launcher_pid -ne $launcherProcess.Id) {
                throw "Endpoint launcher PID does not match the owned launcher."
            }
            $apiPid = [int]$endpoint.api_pid
            if ($apiPid -le 0) {
                throw "Endpoint API PID is invalid."
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

function Assert-DiagnosticBundle {
    param(
        [string]$ArchivePath,
        [string]$ExpectedSha256
    )

    if (-not (Test-Path -LiteralPath $ArchivePath -PathType Leaf)) {
        throw "Diagnostic package was not created: $ArchivePath"
    }
    $actualSha256 = (Get-FileHash -LiteralPath $ArchivePath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actualSha256 -ne $ExpectedSha256.ToLowerInvariant()) {
        throw "Diagnostic package SHA256 does not match the API response."
    }

    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $archive = [System.IO.Compression.ZipFile]::OpenRead($ArchivePath)
    $bundleText = New-Object System.Text.StringBuilder
    try {
        $entryNames = @($archive.Entries | ForEach-Object { $_.FullName })
        foreach ($requiredName in @("diagnostic-report.json", "diagnostic-report.md", "README.txt", "manifest.json")) {
            if ($requiredName -notin $entryNames) {
                throw "Diagnostic package is missing $requiredName."
            }
        }
        foreach ($entry in $archive.Entries) {
            if ($entry.FullName.Contains("..") -or $entry.FullName.StartsWith("/") -or $entry.Length -gt 4194304) {
                throw "Diagnostic package contains an unsafe entry: $($entry.FullName)"
            }
            $stream = $entry.Open()
            $reader = [System.IO.StreamReader]::new($stream)
            try {
                [void]$bundleText.AppendLine($reader.ReadToEnd())
            }
            finally {
                $reader.Dispose()
                $stream.Dispose()
            }
        }
    }
    finally {
        $archive.Dispose()
    }

    $text = $bundleText.ToString()
    if ($text.Contains("p02-secret-sentinel")) {
        throw "Diagnostic package leaked the secret sentinel."
    }
    if ($text.Contains($WorkspaceRoot)) {
        throw "Diagnostic package leaked the workspace path."
    }
    if (-not $text.Contains("Bearer ***") -or -not $text.Contains("api_key=***")) {
        throw "Diagnostic package did not contain the expected redaction markers."
    }
}

try {
    New-Item -ItemType Directory -Path $ReportDirectory, $stateRoot, $acceptanceWorkspace, $logRoot -Force | Out-Null
    if (-not (Test-Path -LiteralPath $InstallerPath -PathType Leaf)) {
        throw "Installer was not found: $InstallerPath"
    }
    if (-not (Test-Path -LiteralPath $WorkspaceRoot -PathType Container)) {
        throw "Workspace root was not found: $WorkspaceRoot"
    }

    @(
        "Authorization: Bearer p02-secret-sentinel",
        "api_key=p02-secret-sentinel",
        "workspace=$WorkspaceRoot"
    ) | Set-Content -LiteralPath (Join-Path $logRoot "diagnostic-redaction-fixture.log") -Encoding UTF8

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
        throw "Installer exited with code $($install.ExitCode). Log: $installerLog"
    }
    $installed = $true

    $launcherPath = Join-Path $InstallRoot "scripts\launcher.ps1"
    $releaseRoot = Join-Path $InstallRoot "release"
    if (-not (Test-Path -LiteralPath $launcherPath -PathType Leaf)) {
        throw "Installed launcher was not found: $launcherPath"
    }

    $env:WORKBENCH_WORKSPACE = $acceptanceWorkspace
    $env:WORKBENCH_DIAGNOSTIC_ROOT = $WorkspaceRoot
    $env:WORKBENCH_STATE_ROOT = $stateRoot
    $env:WORKBENCH_LOG_ROOT = $logRoot
    $launcherProcess = Start-Process `
        -FilePath "powershell.exe" `
        -ArgumentList @(
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            $launcherPath,
            "-InstallRoot",
            $releaseRoot,
            "-NoBrowser"
        ) `
        -RedirectStandardOutput (Join-Path $logRoot "launcher.stdout.log") `
        -RedirectStandardError (Join-Path $logRoot "launcher.stderr.log") `
        -PassThru `
        -WindowStyle Hidden

    $baseUrl = Wait-ForEndpoint -TimeoutSeconds $StartupTimeoutSeconds
    $reportResponse = Invoke-RestMethod -Method Post -Uri "$baseUrl/api/diagnostics/run" -TimeoutSec 120
    $report = $reportResponse.data
    $checks = @($report.checks)
    if ($checks.Count -ne $expectedCheckIds.Count) {
        throw "Expected $($expectedCheckIds.Count) checks but received $($checks.Count)."
    }
    $actualCheckIds = @($checks | ForEach-Object { [string]$_.check_id } | Sort-Object -Unique)
    $missingCheckIds = @($expectedCheckIds | Where-Object { $_ -notin $actualCheckIds })
    if ($missingCheckIds.Count -gt 0 -or $actualCheckIds.Count -ne $expectedCheckIds.Count) {
        throw "Diagnostic check identifiers are incomplete or duplicated: $($missingCheckIds -join ', ')"
    }
    $internalFailures = @(
        $checks | Where-Object {
            $_.code -eq "DIAGNOSTIC_PROBE_FAILED" -or $_.code -eq "DIAGNOSTIC_CENTER_UNAVAILABLE"
        }
    )
    if ($internalFailures.Count -gt 0) {
        throw "One or more diagnostic probes failed internally."
    }

    $packageResponse = Invoke-RestMethod -Method Post -Uri "$baseUrl/api/diagnostics/package" -TimeoutSec 120
    $package = $packageResponse.data
    $workspacePrefix = [System.IO.Path]::GetFullPath($WorkspaceRoot).TrimEnd("\") + "\"
    $packagePath = [System.IO.Path]::GetFullPath((Join-Path $WorkspaceRoot ([string]$package.relative_path)))
    if (-not $packagePath.StartsWith($workspacePrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Diagnostic package escaped the workspace root."
    }
    Assert-DiagnosticBundle -ArchivePath $packagePath -ExpectedSha256 ([string]$package.sha256)

    $health = Invoke-WebRequest -UseBasicParsing -Uri "$baseUrl/api/health" -TimeoutSec 5
    if ($health.StatusCode -ne 200) {
        throw "Application health failed after diagnostics."
    }
    $passed = $true
}
catch {
    $failure = $_.Exception.Message
    Write-Output "P02 acceptance error: $failure"
}
finally {
    Stop-OwnedLauncher -BestEffort
    if ($installed) {
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
        }
        catch {
            $passed = $false
            $failure = $_.Exception.Message
            Write-Output "P02 uninstall error: $failure"
        }
    }
    $env:WORKBENCH_WORKSPACE = $previousWorkspace
    $env:WORKBENCH_DIAGNOSTIC_ROOT = $previousDiagnosticRoot
    $env:WORKBENCH_STATE_ROOT = $previousStateRoot
    $env:WORKBENCH_LOG_ROOT = $previousLogRoot
    [ordered]@{
        passed = $passed
        failure = $failure
        installer_path = $InstallerPath
        package_path = $packagePath
        check_count = $expectedCheckIds.Count
    } | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $evidencePath -Encoding UTF8
}

Write-Output "P02 evidence: $evidencePath"
if ($passed) {
    Write-Output "P02_WINDOWS_ACCEPTANCE=PASS"
    exit 0
}
Write-Output "P02_WINDOWS_ACCEPTANCE=BLOCK"
exit 1
