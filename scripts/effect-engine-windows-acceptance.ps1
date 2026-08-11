[CmdletBinding()]
param(
  [string]$ProjectRoot = "",
  [string]$ReferenceVideo = "",
  [switch]$PlanOnly,
  [switch]$ConfirmManualAcceptance
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($ProjectRoot)) {
  $ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
}
if (-not (Test-Path -LiteralPath $ProjectRoot -PathType Container)) {
  throw "Project root does not exist: $ProjectRoot"
}
if ([string]::IsNullOrWhiteSpace($ReferenceVideo)) {
  throw "ReferenceVideo is required and must point to an operator-supplied local fixture."
}
if (-not (Test-Path -LiteralPath $ReferenceVideo -PathType Leaf)) {
  throw "Reference video is missing: $ReferenceVideo"
}

Write-Output "Effect engine Windows acceptance preparation"
Write-Output "Project root: $ProjectRoot"
Write-Output "Reference video: $ReferenceVideo"
Write-Output "Protected install path: F:\app\app"
Write-Output "Protected data path: F:\Video\workspace.db"

if ($PlanOnly) {
  Write-Output "PLAN_ONLY: no installer, GUI, render, or protected data operation was performed."
  exit 0
}

if (-not $ConfirmManualAcceptance) {
  Write-Error "Manual Windows acceptance is required. Re-run with -ConfirmManualAcceptance only while observing the app on a real Windows desktop."
  exit 2
}

Write-Error "This script intentionally does not automate installation or claim GUI acceptance. Follow tests/acceptance/effect-engine-plan.md and record evidence manually."
exit 3
