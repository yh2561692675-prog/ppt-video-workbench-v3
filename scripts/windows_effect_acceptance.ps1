param(
  [string]$Root = (Get-Location).Path,
  [string]$CandidateManifest = "",
  [string]$ArtifactManifest = "",
  [string]$SampleManifest = "",
  [string]$FeaturePolicy = "",
  [string]$DynamicEvidence = "",
  [string]$DynamicOutputRoot = "",
  [string]$DynamicReport = "",
  [string]$InstallRoot = "",
  [string]$WorkspaceRoot = "",
  [string]$DatabasePath = "",
  [string]$ProductionDatabasePath = "",
  [int]$PortStart = 49152,
  [int]$PortEnd = 49252,
  [switch]$RunTests,
  [switch]$RequireEffectsV2,
  [switch]$RequireEffectsFallback
)

$ErrorActionPreference = "Stop"
$helperPath = Join-Path $PSScriptRoot "windows_effect_acceptance_lib.ps1"
. $helperPath

function Invoke-SourcePython {
  param(
    [Parameter(Mandatory = $true)]
    [string[]]$Arguments
  )

  $uv = Get-Command uv -ErrorAction SilentlyContinue
  if ($null -ne $uv) {
    & $uv.Source run python @Arguments
  } else {
    & python @Arguments
  }
}

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

$dynamicInputs = @($CandidateManifest, $ArtifactManifest, $SampleManifest, $FeaturePolicy, $DynamicEvidence, $DynamicReport)
$hasDynamicInputs = @($dynamicInputs | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
if ($hasDynamicInputs.Count -gt 0 -and $hasDynamicInputs.Count -ne $dynamicInputs.Count) {
  throw "E_DYNAMIC_INPUTS: candidate, artifact, sample, evidence and report paths are all required"
}
if ($hasDynamicInputs.Count -eq $dynamicInputs.Count) {
  foreach ($path in @($CandidateManifest, $ArtifactManifest, $SampleManifest, $FeaturePolicy, $DynamicEvidence)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
      throw "E_DYNAMIC_INPUTS: required file is missing: $path"
    }
  }
  if ([string]::IsNullOrWhiteSpace($DynamicOutputRoot)) {
    $DynamicOutputRoot = Join-Path $WorkspaceRoot "dynamic-output"
  }
  New-Item -ItemType Directory -Path $DynamicOutputRoot -Force | Out-Null
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
Invoke-SourcePython -Arguments @("$Root\scripts\verify_effect_release.py", "--root", $Root)
if ($LASTEXITCODE -ne 0) {
  throw "E_RELEASE_VERIFY: release verification failed"
}

if ($RunTests) {
  Push-Location $Root
  try {
    $env:CI = "true"
    Invoke-SourcePython -Arguments @("-m", "pytest", "-q", "--import-mode=importlib")
    if ($LASTEXITCODE -ne 0) { throw "E_TESTS: pytest failed" }
    & pnpm --filter "@workbench/web" run typecheck
    if ($LASTEXITCODE -ne 0) { throw "E_TESTS: web typecheck failed" }
    & pnpm --filter "@workbench/web" run test -- --run
    if ($LASTEXITCODE -ne 0) { throw "E_TESTS: web tests failed" }
    & pnpm --filter "@workbench/remotion" run typecheck
    if ($LASTEXITCODE -ne 0) { throw "E_TESTS: remotion typecheck failed" }
    & pnpm --filter "@workbench/remotion" run test
    if ($LASTEXITCODE -ne 0) { throw "E_TESTS: remotion tests failed" }
  } finally {
    Pop-Location
  }
}

if ($hasDynamicInputs.Count -eq $dynamicInputs.Count) {
  $dynamicArguments = @(
    (Join-Path $Root "scripts\effects_dynamic_acceptance.py"),
    "--candidate-manifest", $CandidateManifest,
    "--feature-policy", $FeaturePolicy,
    "--evidence", $DynamicEvidence,
    "--output-root", $DynamicOutputRoot,
    "--output", $DynamicReport
  )
  if ($RequireEffectsV2) { $dynamicArguments += "--require-v2" }
  if ($RequireEffectsFallback) { $dynamicArguments += "--require-fallback" }
  Invoke-SourcePython -Arguments $dynamicArguments
  if ($LASTEXITCODE -ne 0) {
    throw "E_DYNAMIC_ACCEPTANCE: Effects dynamic evidence failed"
  }
  Write-EvidenceRecord -EvidencePath $evidencePath -Step "effects_dynamic_acceptance" -Result "passed" -Details @{
    candidate_manifest = $CandidateManifest
    artifact_manifest = $ArtifactManifest
    sample_manifest = $SampleManifest
    report = $DynamicReport
  }
}

Write-EvidenceRecord -EvidencePath $evidencePath -Step "release-tests" -Result "passed" -Details @{ run_tests = [bool]$RunTests }
Write-Host "Release integrity passed. Complete the Windows checklist in docs/effects/windows-acceptance-report.md."
