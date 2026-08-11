[CmdletBinding()]
param(
    [string]$InstallRoot = (Split-Path -Parent $PSScriptRoot),
    [switch]$NoBrowser,
    [int]$StartupTimeoutSeconds = 30
)

$ErrorActionPreference = "Stop"

$stateRoot = if ([string]::IsNullOrWhiteSpace($env:WORKBENCH_STATE_ROOT)) {
    Join-Path $env:LOCALAPPDATA "PPTVideoWorkbench"
}
else {
    $env:WORKBENCH_STATE_ROOT
}
$logRoot = if ([string]::IsNullOrWhiteSpace($env:WORKBENCH_LOG_ROOT)) {
    $stateRoot
}
else {
    $env:WORKBENCH_LOG_ROOT
}
$workspaceRoot = if ([string]::IsNullOrWhiteSpace($env:WORKBENCH_WORKSPACE)) {
    Join-Path $stateRoot "workspace-data"
}
else {
    $env:WORKBENCH_WORKSPACE
}
$cacheRoot = "F:\Video\Cache"
if (-not [string]::IsNullOrWhiteSpace($env:WORKBENCH_CACHE_ROOT)) {
    $cacheRoot = $env:WORKBENCH_CACHE_ROOT
}
$outputRoot = "F:\Video\Output"
if (-not [string]::IsNullOrWhiteSpace($env:WORKBENCH_OUTPUT_ROOT)) {
    $outputRoot = $env:WORKBENCH_OUTPUT_ROOT
}
$lockPath = Join-Path $stateRoot "workbench.lock"
$endpointPath = Join-Path $stateRoot "endpoint.json"
$apiExecutable = Join-Path $InstallRoot "api\workbench.exe"
$apiWorkingDirectory = Join-Path $InstallRoot "api"
$webRoot = Join-Path $InstallRoot "web"
$runtimeRoot = Join-Path $InstallRoot "runtime"
$peripheralExecutable = Join-Path $InstallRoot "peripheral\peripheral-host.exe"
$peripheralInitialize = Join-Path $InstallRoot "peripheral\scripts\initialize-s0.ps1"
$process = $null
$peripheralProcess = $null
$lockHandle = $null
$apiStdout = Join-Path $logRoot ("api-" + $PID + ".stdout.log")
$apiStderr = Join-Path $logRoot ("api-" + $PID + ".stderr.log")

function Get-FreeLocalPort {
    $listener = [System.Net.Sockets.TcpListener]::new(
        [System.Net.IPAddress]::Parse("127.0.0.1"),
        0
    )
    try {
        $listener.Start()
        return ([System.Net.IPEndPoint]$listener.LocalEndpoint).Port
    }
    finally {
        $listener.Stop()
    }
}

function Acquire-InstanceLock {
    param([string]$Path)

    New-Item -ItemType Directory -Path (Split-Path -Parent $Path) -Force | Out-Null
    try {
        $handle = [System.IO.File]::Open(
            $Path,
            [System.IO.FileMode]::CreateNew,
            [System.IO.FileAccess]::ReadWrite,
            [System.IO.FileShare]::None
        )
        $bytes = [System.Text.Encoding]::UTF8.GetBytes([string]$PID)
        $handle.Write($bytes, 0, $bytes.Length)
        $handle.Flush()
        return $handle
    }
    catch [System.IO.IOException] {
        $existingPid = 0
        try {
            $existingPid = [int](Get-Content -LiteralPath $Path -Raw)
        }
        catch {
            # A concurrently-created lock is still treated as active.
        }
        if ($existingPid -gt 0 -and (Get-Process -Id $existingPid -ErrorAction SilentlyContinue)) {
            throw "PPT Video Workbench is already running (process $existingPid)."
        }
        Remove-Item -LiteralPath $Path -Force -ErrorAction SilentlyContinue
        return Acquire-InstanceLock -Path $Path
    }
}

function Wait-ForHealth {
    param(
        [int]$Port,
        [int]$TimeoutSeconds
    )

    $healthUri = "http://127.0.0.1:$Port/api/health"
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if ($null -ne $process -and $process.HasExited) {
            throw "API process exited with code $($process.ExitCode). Diagnostics: stdout=$apiStdout; stderr=$apiStderr"
        }
        try {
            $response = Invoke-WebRequest -UseBasicParsing -Uri $healthUri -TimeoutSec 2
            if ($response.StatusCode -eq 200) {
                return $healthUri
            }
        }
        catch {
            Start-Sleep -Milliseconds 250
        }
    }
    throw "API health check timed out: $healthUri"
}

function Assert-WritableDirectory {
    param([string]$Path)

    New-Item -ItemType Directory -Path $Path -Force | Out-Null
    if (-not (Test-Path -LiteralPath $Path -PathType Container)) {
        throw "Configured storage path is not a directory: $Path"
    }
    $probe = Join-Path $Path (".ppt-video-workbench-write-probe-" + [guid]::NewGuid().ToString("N") + ".tmp")
    try {
        [System.IO.File]::WriteAllText($probe, "probe")
    }
    catch {
        throw "Configured storage path is not writable: $Path"
    }
    finally {
        Remove-Item -LiteralPath $probe -Force -ErrorAction SilentlyContinue
    }
}

function Wait-ForPeripheralHealth {
    $healthUri = "http://127.0.0.1:8765/internal/v1/health"
    $deadline = (Get-Date).AddSeconds(10)
    while ((Get-Date) -lt $deadline) {
        try {
            $response = Invoke-RestMethod -Uri $healthUri -TimeoutSec 2
            if ($response.status -eq "ok" -and $response.schema_version -eq "1.0") {
                return $true
            }
        }
        catch {
            Start-Sleep -Milliseconds 250
        }
    }
    return $false
}

function Stop-OwnedProcess {
    param([System.Diagnostics.Process]$OwnedProcess)
    if ($OwnedProcess -and -not $OwnedProcess.HasExited) {
        $OwnedProcess.CloseMainWindow() | Out-Null
        if (-not $OwnedProcess.WaitForExit(3000)) {
            Stop-Process -Id $OwnedProcess.Id -Force -ErrorAction SilentlyContinue
        }
    }
}

try {
    New-Item -ItemType Directory -Path $logRoot -Force | Out-Null
    Assert-WritableDirectory -Path $cacheRoot
    Assert-WritableDirectory -Path $outputRoot
    if (-not (Test-Path -LiteralPath $apiExecutable -PathType Leaf)) {
        throw "Installed API runtime was not found: $apiExecutable"
    }
    if (-not (Test-Path -LiteralPath (Join-Path $webRoot "index.html") -PathType Leaf)) {
        throw "Installed Web UI was not found: $webRoot"
    }
    if (-not (Test-Path -LiteralPath (Join-Path $runtimeRoot "node\node.exe") -PathType Leaf)) {
        throw "Installed rendering runtime was not found: $runtimeRoot"
    }

    $lockHandle = Acquire-InstanceLock -Path $lockPath
    $port = Get-FreeLocalPort
    $env:WORKBENCH_WORKSPACE = $workspaceRoot
    $env:WORKBENCH_CACHE_ROOT = $cacheRoot
    $env:WORKBENCH_OUTPUT_ROOT = $outputRoot
    $env:WORKBENCH_WEB_ROOT = $webRoot
    $env:WORKBENCH_RUNTIME_ROOT = $runtimeRoot
    $env:WORKBENCH_FFMPEG = Join-Path $runtimeRoot "ffmpeg\ffmpeg.exe"
    $env:WORKBENCH_FFPROBE = Join-Path $runtimeRoot "ffmpeg\ffprobe.exe"
    $env:PERIPHERAL_DEGRADED = "false"
    if ($env:PERIPHERAL_ENABLED -eq "true") {
        try {
            if (-not (Test-Path -LiteralPath $peripheralInitialize -PathType Leaf)) {
                throw "Peripheral workspace initializer was not found."
            }
            if (-not (Test-Path -LiteralPath $peripheralExecutable -PathType Leaf)) {
                throw "Peripheral host executable was not found."
            }
            & $peripheralInitialize -WorkspaceRoot $workspaceRoot
            if ($LASTEXITCODE -ne 0) {
                throw "Peripheral workspace initialization failed."
            }
            $peripheralProcess = Start-Process `
                -FilePath $peripheralExecutable `
                -WorkingDirectory (Split-Path -Parent $peripheralExecutable) `
                -PassThru `
                -WindowStyle Hidden
            if (-not (Wait-ForPeripheralHealth)) {
                throw "Peripheral host health check timed out."
            }
        }
        catch {
            $env:PERIPHERAL_DEGRADED = "true"
            Stop-OwnedProcess -OwnedProcess $peripheralProcess
            $peripheralProcess = $null
            Write-Warning "Peripheral host is degraded; the main workflow will continue."
        }
    }
    $arguments = @(
        "serve",
        "--host", "127.0.0.1",
        "--port", [string]$port
    )
    $process = Start-Process `
        -FilePath $apiExecutable `
        -ArgumentList $arguments `
        -WorkingDirectory $apiWorkingDirectory `
        -RedirectStandardOutput $apiStdout `
        -RedirectStandardError $apiStderr `
        -PassThru `
        -WindowStyle Hidden

    $healthUri = Wait-ForHealth -Port $port -TimeoutSeconds $StartupTimeoutSeconds
    [ordered]@{
        base_url = "http://127.0.0.1:$port"
        health_url = $healthUri
        launcher_pid = $PID
        api_pid = $process.Id
    } |
        ConvertTo-Json | Set-Content -LiteralPath $endpointPath -Encoding UTF8
    if (-not $NoBrowser) {
        Start-Process "http://127.0.0.1:$port/"
    }
    Wait-Process -Id $process.Id
}
finally {
    Stop-OwnedProcess -OwnedProcess $process
    if ($peripheralProcess -and -not $peripheralProcess.HasExited) {
        $ownedPeripheralId = $peripheralProcess.Id
        Stop-OwnedProcess -OwnedProcess $peripheralProcess
        Write-Output "Stopped owned peripheral process $ownedPeripheralId."
    }
    if ($lockHandle) {
        $lockHandle.Dispose()
    }
    Remove-Item -LiteralPath $lockPath -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $endpointPath -Force -ErrorAction SilentlyContinue
}
