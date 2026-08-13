param(
    [string]$Config,
    [string]$Candidate,
    [string]$Ffmpeg,
    [string]$Ffprobe,
    [string]$Uv,
    [int]$DurationSeconds = 7200,
    [int]$MinimumCycles = 100,
    [int]$CycleIntervalSeconds = 15,
    [int]$PageCount = 2,
    [int]$RecoveryEvery = 3,
    [int]$CancellationEvery = 5,
    [int]$RetainCompletedJobs = 2,
    [int]$LedgerSegmentBytes = 262144
)

$ErrorActionPreference = 'Stop'
if ($Config) {
    $configPath = Resolve-Path -LiteralPath $Config
    $scheduledConfig = Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json
    $Candidate = [string]$scheduledConfig.candidate
    $Ffmpeg = [string]$scheduledConfig.ffmpeg
    $Ffprobe = [string]$scheduledConfig.ffprobe
    $Uv = [string]$scheduledConfig.uv
    $DurationSeconds = [int]$scheduledConfig.duration_seconds
    $MinimumCycles = [int]$scheduledConfig.minimum_cycles
    $CycleIntervalSeconds = [int]$scheduledConfig.cycle_interval_seconds
    $PageCount = [int]$scheduledConfig.page_count
    $RecoveryEvery = [int]$scheduledConfig.recovery_every
    $CancellationEvery = [int]$scheduledConfig.cancellation_every
    if ($null -ne $scheduledConfig.retain_completed_jobs) {
        $RetainCompletedJobs = [int]$scheduledConfig.retain_completed_jobs
    }
    $LedgerSegmentBytes = [int]$scheduledConfig.ledger_segment_bytes
}
foreach ($requiredValue in @($Candidate, $Ffmpeg, $Ffprobe, $Uv)) {
    if ([string]::IsNullOrWhiteSpace($requiredValue)) {
        throw 'Candidate, Ffmpeg, Ffprobe, and Uv are required (directly or through -Config).'
    }
}
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

$logRoot = Join-Path $repoRoot 'test-results\soak\long-runs'
New-Item -ItemType Directory -Path $logRoot -Force | Out-Null
$runStamp = Get-Date -Format 'yyyyMMddTHHmmssZ'
$logPrefix = Join-Path $logRoot "dp45-soak-scheduled-$runStamp"
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
    retain_completed_jobs = $RetainCompletedJobs
} | ConvertTo-Json | Set-Content -LiteralPath $startedPath -Encoding utf8

$previousErrorActionPreference = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
try {
    & $Uv run python scripts/performance_soak_acceptance.py `
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
        --retain-completed-jobs $RetainCompletedJobs `
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
