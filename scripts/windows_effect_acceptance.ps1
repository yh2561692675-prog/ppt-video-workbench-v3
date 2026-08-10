param(
  [string]$Root = (Get-Location).Path,
  [string]$InstallRoot = "",
  [string]$WorkspaceRoot = "",
  [string]$DatabasePath = "",
  [string]$ProductionDatabasePath = "",
  [int]$PortStart = 49152,
  [int]$PortEnd = 49252,
  [switch]$RunTests
)

$ErrorActionPreference = "Stop"
$helperPath = Join-Path $PSScriptRoot "windows_effect_acceptance_lib.ps1"
. $helperPath

if ([string]::IsNullOrWhiteSpace($InstallRoot)) {
  $InstallRoot = Join-Path $Root "acceptance-app"
}
if ([string]::IsNullOrWhiteSpace($WorkspaceRoot)) {
  $WorkspaceRoot = Join-Path $Root "acceptance-workspace"
}
if ([string]::IsNullOrWhiteSpace($DatabasePath)) {
  $DatabasePath = Join-Path $WorkspaceRoot "workspace.db"
}
if ([string]::IsNullOrWhiteSpace($ProductionDatabasePath)) {
  if (-not [string]::IsNullOrWhiteSpace($env:WORKBENCH_PRODUCTION_DATABASE)) {
    $ProductionDatabasePath = $env:WORKBENCH_PRODUCTION_DATABASE
  } elseif (-not [string]::IsNullOrWhiteSpace($env:WORKBENCH_WORKSPACE)) {
    $ProductionDatabasePath = Join-Path $env:WORKBENCH_WORKSPACE "workspace.db"
  } else {
    $ProductionDatabasePath = "F:\Video\workspace.db"
  }
}

$isolation = Assert-AcceptanceIsolation `
  -Root $Root `
  -InstallRoot $InstallRoot `
  -WorkspaceRoot $WorkspaceRoot `
  -DatabasePath $DatabasePath `
  -ProductionDatabasePath $ProductionDatabasePath
$port = Get-FreeAcceptancePort -StartPort $PortStart -EndPort $PortEnd
New-Item -ItemType Directory -Path $isolation.install_root -Force | Out-Null
New-Item -ItemType Directory -Path $isolation.workspace_root -Force | Out-Null
$evidencePath = Join-Path $isolation.workspace_root "acceptance-evidence.jsonl"
Write-EvidenceRecord -EvidencePath $evidencePath -Step "isolation" -Result "passed" -Details @{
  install_root = $isolation.install_root
  workspace_root = $isolation.workspace_root
  database_path = $isolation.database_path
  port = $port
}

Write-Host "Verifying effect release from $Root"
& python "$Root\scripts\verify_effect_release.py" --root $Root
if ($LASTEXITCODE -ne 0) {
  throw "E_RELEASE_VERIFY: release verification failed"
}

if ($RunTests) {
  Push-Location $Root
  try {
    & python -m pytest -q
    if ($LASTEXITCODE -ne 0) { throw "E_TESTS: pytest failed" }
    & pnpm --dir "$Root\apps\web" run typecheck
    if ($LASTEXITCODE -ne 0) { throw "E_TESTS: web typecheck failed" }
    & pnpm --dir "$Root\apps\web" run test -- --run
    if ($LASTEXITCODE -ne 0) { throw "E_TESTS: web tests failed" }
    & pnpm --dir "$Root\remotion" run typecheck
    if ($LASTEXITCODE -ne 0) { throw "E_TESTS: remotion typecheck failed" }
    & pnpm --dir "$Root\remotion" run test
    if ($LASTEXITCODE -ne 0) { throw "E_TESTS: remotion tests failed" }
  } finally {
    Pop-Location
  }
}

Write-EvidenceRecord -EvidencePath $evidencePath -Step "release-tests" -Result "passed" -Details @{ run_tests = [bool]$RunTests }
Write-Host "Release integrity passed. Complete the Windows checklist in docs/effects/windows-acceptance-report.md."
