[CmdletBinding()]
param(
    [string]$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")),
    [string]$WindowsAcceptanceReport = ""
)

$ErrorActionPreference = "Stop"
$manifestPath = Join-Path $Root "tests/acceptance/results/RC1/evidence-manifest.json"
$signoffPath = Join-Path $Root "docs/acceptance-signoff-v1.0.md"
$releaseNotesPath = Join-Path $Root "docs/release-notes-v1.0.md"

if (-not [string]::IsNullOrWhiteSpace($WindowsAcceptanceReport)) {
    if (-not (Test-Path -LiteralPath $WindowsAcceptanceReport -PathType Leaf)) {
        throw "Release blocked: P01 Windows acceptance report is missing: $WindowsAcceptanceReport"
    }
    $windowsAcceptance = Get-Content -LiteralPath $WindowsAcceptanceReport -Raw | ConvertFrom-Json
    if (
        $windowsAcceptance.schema_version -ne "1.0" -or
        $windowsAcceptance.decision -ne "pass" -or
        @($windowsAcceptance.blocking_failures).Count -ne 0
    ) {
        throw "Release blocked: P01 Windows acceptance is not passed."
    }
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
