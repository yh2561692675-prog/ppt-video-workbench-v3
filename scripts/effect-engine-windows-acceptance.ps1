[CmdletBinding()]
param(
  [string]$ProjectRoot = "F:\ppt-video-workbench-v3",
  [string]$ReferenceVideo = "D:\xwechat_files\wxid_vwiv5x4loccs22_022f\msg\video\2026-08\383a9d3f7e55836a06ae49292ddaf54b.mp4",
  [switch]$PlanOnly,
  [switch]$ConfirmManualAcceptance
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $ProjectRoot -PathType Container)) {
  throw "Project root does not exist: $ProjectRoot"
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
