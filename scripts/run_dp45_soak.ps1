param(
    [Parameter(Mandatory = $true)]
    [string]$Candidate,
    [Parameter(Mandatory = $true)]
    [string]$Ffmpeg,
    [Parameter(Mandatory = $true)]
    [string]$Ffprobe,
    [int]$DurationSeconds = 7200,
    [int]$MinimumCycles = 100,
    [int]$CycleIntervalSeconds = 15,
    [int]$PageCount = 2,
    [int]$RecoveryEvery = 3,
    [int]$CancellationEvery = 5,
    [int]$LedgerSegmentBytes = 262144
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

$logRoot = Join-Path $repoRoot 'test-results\soak\long-runs'
New-Item -ItemType Directory -Path $logRoot -Force | Out-Null
$runStamp = Get-Date -Format 'yyyyMMddTHHmmssZ'
$logPrefix = Join-Path $logRoot "dp45-2h-scheduled-$runStamp"
$startedPath = "$logPrefix.started.json"
$completedPath = "$logPrefix.completed.json"

[ordered]@{
    schema_version = '1.0'
    status = 'running'
    started_at_utc = (Get-Date).ToUniversalTime().ToString('o')
    candidate = (Resolve-Path -LiteralPath $Candidate).Path
    duration_seconds = $DurationSeconds
    minimum_cycles = $MinimumCycles
    cycle_interval_seconds = $CycleIntervalSeconds
    page_count = $PageCount
    recovery_every = $RecoveryEvery
    cancellation_every = $CancellationEvery
} | ConvertTo-Json | Set-Content -LiteralPath $startedPath -Encoding utf8

$previousErrorActionPreference = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
try {
    & uv run python scripts/performance_soak_acceptance.py `
        --candidate $Candidate `
        --repo-root . `
        --output-root test-results/soak `
        --ffmpeg $Ffmpeg `
        --ffprobe $Ffprobe `
        --duration-seconds $DurationSeconds `
        --minimum-cycles $MinimumCycles `
        --cycle-interval-seconds $CycleIntervalSeconds `
        --page-count $PageCount `
        --recovery-every $RecoveryEvery `
        --cancellation-every $CancellationEvery `
        --ledger-segment-bytes $LedgerSegmentBytes *>> "$logPrefix.output.log"
    $exitCode = $LASTEXITCODE
}
finally {
    $ErrorActionPreference = $previousErrorActionPreference
}

[ordered]@{
    schema_version = '1.0'
    status = if ($exitCode -eq 0) { 'passed' } else { 'failed' }
    finished_at_utc = (Get-Date).ToUniversalTime().ToString('o')
    exit_code = $exitCode
    candidate = (Resolve-Path -LiteralPath $Candidate).Path
    output_log = "$logPrefix.output.log"
} | ConvertTo-Json | Set-Content -LiteralPath $completedPath -Encoding utf8

exit $exitCode
