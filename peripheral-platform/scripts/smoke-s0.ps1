[CmdletBinding()]
param(
    [string]$WorkspaceRoot = (Join-Path $env:TEMP "PPTVideoWorkbench-S0-Smoke"),
    [string]$ReleaseRoot = "dist/release",
    [int]$StartupTimeoutSeconds = 10
)

$ErrorActionPreference = "Stop"
$platformRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$repoRoot = Resolve-Path (Join-Path $platformRoot "..")
$resolvedReleaseRoot = Join-Path $repoRoot $ReleaseRoot
$executable = Join-Path $resolvedReleaseRoot "peripheral\peripheral-host.exe"
$process = $null

function Get-AvailableLoopbackPort {
    $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, 0)
    try {
        $listener.Start()
        return ([System.Net.IPEndPoint]$listener.LocalEndpoint).Port
    }
    finally {
        $listener.Stop()
    }
}

function Wait-ForPeripheralHealth {
    param(
        [int]$TimeoutSeconds,
        [System.Diagnostics.Process]$OwnedProcess,
        [string]$baseUrl,
        [string]$StandardOutputPath,
        [string]$StandardErrorPath
    )
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $lastFailure = $null
    while ((Get-Date) -lt $deadline) {
        if ($OwnedProcess.HasExited) {
            throw "S0 host process exited before becoming healthy (exit code $($OwnedProcess.ExitCode)). Diagnostics: $StandardOutputPath; $StandardErrorPath"
        }
        try {
            $health = Invoke-RestMethod `
                -Uri "$baseUrl/health" -TimeoutSec 2
            if ($health.status -eq "ok" -and $health.schema_version -eq "1.0") {
                return
            }
        }
        catch {
            $lastFailure = $_.Exception.Message
        }
        Start-Sleep -Milliseconds 250
    }
    throw "S0 health check timed out while the host process remained running. Last probe failure: $lastFailure. Diagnostics: $StandardOutputPath; $StandardErrorPath"
}

function Stop-OwnedProcess {
    param([System.Diagnostics.Process]$OwnedProcess)
    if ($OwnedProcess -and -not $OwnedProcess.HasExited) {
        $OwnedProcess.CloseMainWindow() | Out-Null
        if (-not $OwnedProcess.WaitForExit(3000)) {
            Stop-Process -Id $OwnedProcess.Id -Force -ErrorAction SilentlyContinue
            $OwnedProcess.WaitForExit(3000) | Out-Null
        }
    }
}

try {
    & (Join-Path $PSScriptRoot "initialize-s0.ps1") -WorkspaceRoot $WorkspaceRoot
    if ($LASTEXITCODE -ne 0) {
        throw "S0 workspace initialization failed."
    }
    if (-not (Test-Path -LiteralPath $executable -PathType Leaf)) {
        throw "S0 executable was not found: $executable"
    }
    $env:WORKBENCH_WORKSPACE = $WorkspaceRoot
    $env:PERIPHERAL_ENABLED = "true"
    $env:PERIPHERAL_HOST = "127.0.0.1"
    $port = Get-AvailableLoopbackPort
    $env:PERIPHERAL_PORT = [string]$port
    $baseUrl = "http://127.0.0.1:$port/internal/v1"
    $diagnosticsRoot = Join-Path $WorkspaceRoot "diagnostics"
    $standardOutputPath = Join-Path $diagnosticsRoot "peripheral-host.stdout.log"
    $standardErrorPath = Join-Path $diagnosticsRoot "peripheral-host.stderr.log"
    Remove-Item -LiteralPath $standardOutputPath, $standardErrorPath -Force -ErrorAction SilentlyContinue
    $process = Start-Process -FilePath $executable -WorkingDirectory `
        (Split-Path -Parent $executable) -PassThru -WindowStyle Hidden `
        -RedirectStandardOutput $standardOutputPath -RedirectStandardError $standardErrorPath
    Wait-ForPeripheralHealth -TimeoutSeconds $StartupTimeoutSeconds -OwnedProcess $process `
        -BaseUrl $baseUrl `
        -StandardOutputPath $standardOutputPath -StandardErrorPath $standardErrorPath

    $jobId = [guid]::NewGuid().ToString()
    $body = [ordered]@{
        schema_version = "1.0"
        job_id = $jobId
        project_id = [guid]::NewGuid().ToString()
        job_type = "system.echo"
        requested_by = "smoke-s0"
        priority = 50
        idempotency_key = [guid]::NewGuid().ToString("N")
        inputs = @()
        parameters = @{ text = "S0 smoke" }
        created_at = [DateTimeOffset]::UtcNow.ToString("o")
    } | ConvertTo-Json -Depth 5
    Invoke-RestMethod -Method Post -ContentType "application/json" `
        -Uri "$baseUrl/jobs" -Body $body | Out-Null

    $deadline = (Get-Date).AddSeconds(15)
    do {
        Start-Sleep -Milliseconds 250
        $status = Invoke-RestMethod `
            -Uri "$baseUrl/jobs/$jobId" -TimeoutSec 2
    } while ($status.status -notin @("succeeded", "failed", "cancelled") -and (Get-Date) -lt $deadline)
    if ($status.status -ne "succeeded") {
        throw "S0 Echo smoke job did not succeed: $($status.status)"
    }
    $artifacts = @(Invoke-RestMethod `
        -Uri "$baseUrl/jobs/$jobId/artifacts" -TimeoutSec 2)
    if ($artifacts.Count -ne 1 -or $artifacts[0].logical_name -ne "echo-text") {
        throw "S0 Echo smoke artifact was not published."
    }
    Write-Output "S0 smoke passed: health, Echo job, artifact publication."
}
finally {
    Stop-OwnedProcess -OwnedProcess $process
}
