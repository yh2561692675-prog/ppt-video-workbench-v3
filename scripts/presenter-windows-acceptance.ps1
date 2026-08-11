[CmdletBinding()]
param(
  [string]$ProjectRoot = "F:\ppt-video-workbench-v3",
  [string]$StandardVideo = "",
  [string]$LongVideo = "",
  [string]$EvidenceRoot = "",
  [switch]$PlanOnly,
  [switch]$ConfirmManualAcceptance
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $ProjectRoot -PathType Container)) {
  throw "Project root does not exist: $ProjectRoot"
}

$fixtureManifest = Join-Path $ProjectRoot "tests\fixtures\presenter\manifest.json"
$acceptancePlan = Join-Path $ProjectRoot "tests\acceptance\presenter-mode-plan.md"
if (-not (Test-Path -LiteralPath $fixtureManifest -PathType Leaf)) {
  throw "Presenter fixture manifest is missing: $fixtureManifest"
}
if (-not (Test-Path -LiteralPath $acceptancePlan -PathType Leaf)) {
  throw "Presenter acceptance plan is missing: $acceptancePlan"
}

Write-Output "Presenter mode Windows acceptance preparation"
Write-Output "Project root: $ProjectRoot"
Write-Output "Fixture manifest: $fixtureManifest"
Write-Output "Acceptance plan: $acceptancePlan"
Write-Output "Release flag required before sign-off: internal"

if ($PlanOnly) {
  Write-Output "PLAN_ONLY: no installer, GUI, ASR, render, or private media operation was performed."
  exit 0
}

foreach ($fixture in @($StandardVideo, $LongVideo)) {
  if ([string]::IsNullOrWhiteSpace($fixture) -or -not (Test-Path -LiteralPath $fixture -PathType Leaf)) {
    throw "Both StandardVideo and LongVideo must resolve to local private fixture files."
  }
}
if ([string]::IsNullOrWhiteSpace($EvidenceRoot)) {
  throw "EvidenceRoot is required for manual acceptance."
}
if (-not (Test-Path -LiteralPath $EvidenceRoot -PathType Container)) {
  throw "Evidence root does not exist: $EvidenceRoot"
}
if (-not $ConfirmManualAcceptance) {
  Write-Error "Manual Windows acceptance is required. Observe the RC app and follow presenter-mode-plan.md."
  exit 2
}

Write-Error "This script validates preparation only and cannot claim operator, audiovisual, recovery, or antivirus acceptance. Record evidence manually."
exit 3
