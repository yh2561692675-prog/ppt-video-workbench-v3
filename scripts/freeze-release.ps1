[CmdletBinding()]
param(
    [string]$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")),
    [Parameter(Mandatory = $true)]
    [string]$WindowsAcceptanceReport,
    [Parameter(Mandatory = $true)]
    [string]$ReleaseArtifactManifest
)

$ErrorActionPreference = "Stop"
$manifestPath = Join-Path $Root "tests/acceptance/results/RC1/evidence-manifest.json"
$signoffPath = Join-Path $Root "docs/acceptance-signoff-v1.0.md"
$releaseNotesPath = Join-Path $Root "docs/release-notes-v1.0.md"

if (-not (Test-Path -LiteralPath $WindowsAcceptanceReport -PathType Leaf)) {
    throw "Release blocked: Windows full-chain acceptance report is missing: $WindowsAcceptanceReport"
}
if (-not (Test-Path -LiteralPath $ReleaseArtifactManifest -PathType Leaf)) {
    throw "Release blocked: release artifact manifest is missing: $ReleaseArtifactManifest"
}
$windowsAcceptance = Get-Content -LiteralPath $WindowsAcceptanceReport -Raw | ConvertFrom-Json
$releaseArtifacts = Get-Content -LiteralPath $ReleaseArtifactManifest -Raw | ConvertFrom-Json
$acceptanceEvidenceManifest = Join-Path (Split-Path -Parent $WindowsAcceptanceReport) "evidence-manifest.json"
if (
    $windowsAcceptance.schema_version -ne "2.0" -or
    $windowsAcceptance.decision -ne "pass" -or
    @($windowsAcceptance.blocking_failures).Count -ne 0 -or
    -not $windowsAcceptance.evidence -or
    -not $windowsAcceptance.evidence.release -or
    $windowsAcceptance.evidence.release.execution_mode -ne "physical_windows" -or
    $windowsAcceptance.evidence.release.candidate_id -ne $releaseArtifacts.candidate_id
) {
    throw "Release blocked: P01 Windows acceptance is not passed; a physical schema 2.0 full-chain report is required for this candidate."
}
if (-not (Test-Path -LiteralPath $acceptanceEvidenceManifest -PathType Leaf)) {
    throw "Release blocked: Windows acceptance evidence manifest is missing."
}
$requiredPhaseNames = @(
    "artifact_resolution", "clean_install", "first_launch", "legacy_project",
    "interruption_recovery", "full_preflight", "play_from_start", "final_export",
    "uninstall_reinstall", "version_rollback", "process_cleanup", "workspace_retention"
)
foreach ($phaseName in $requiredPhaseNames) {
    $phase = $windowsAcceptance.evidence.phases.$phaseName
    if ($null -eq $phase -or $phase.result -ne "passed" -or @($phase.evidence_refs).Count -eq 0) {
        throw "Release blocked: Windows acceptance phase '$phaseName' is incomplete."
    }
}
$finishedAt = [DateTimeOffset]::Parse([string]$windowsAcceptance.evidence.phases.full_preflight.finished_at)
if ($finishedAt -lt [DateTimeOffset]::UtcNow.AddDays(-7)) {
    throw "Release blocked: Windows acceptance report is older than seven days."
}

if (-not (Test-Path $manifestPath)) {
    throw "RC1 evidence manifest is missing: $manifestPath"
}

$evidence = Get-Content -Raw -Path $manifestPath | ConvertFrom-Json
if ($evidence.status -eq "pending_manual_windows") {
    throw "Release blocked: RC1 is pending_manual_windows."
}
if ($evidence.status -ne "signed" -or $evidence.signoff."signed" -ne $true) {
    throw "Release blocked: RC1 sign-off must be signed before v1.0.0 freeze."
}

foreach ($defectId in @("P0", "P1")) {
    if ($evidence.defects.$defectId -in @("not_assessed", "open", "blocked")) {
        throw "Release blocked: $defectId defects are not release-ready."
    }
}

foreach ($artifact in $evidence.artifacts) {
    if ($artifact.result -ne "passed") {
        throw "Release blocked: artifact '$($artifact.name)' is not passed."
    }
}
foreach ($scenario in $evidence.scenarios) {
    if ($scenario.result -ne "passed") {
        throw "Release blocked: scenario '$($scenario.id)' is not passed."
    }
}

foreach ($requiredPath in @($signoffPath, $releaseNotesPath)) {
    if (-not (Test-Path $requiredPath)) {
        throw "Release documentation is missing: $requiredPath"
    }
}

Write-Output "V1.0.0 release freeze checks passed."
