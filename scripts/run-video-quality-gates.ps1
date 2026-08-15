[CmdletBinding()]
param(
  [Alias('Input')]
  [string]$VideoInput = '',
  [string]$OutputRoot = '',
  [string]$CandidateManifest = '',
  [string]$TargetManifest = '',
  [string]$FfmpegDir = ''
)

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$python = Join-Path $repoRoot '.venv\Scripts\python.exe'
$remotionVitest = Join-Path $repoRoot 'remotion\node_modules\.bin\vitest.CMD'
$tsc = Join-Path $repoRoot 'node_modules\.bin\tsc.cmd'

Push-Location $repoRoot
try {

if (-not [string]::IsNullOrWhiteSpace($VideoInput) -or
    -not [string]::IsNullOrWhiteSpace($CandidateManifest) -or
    -not [string]::IsNullOrWhiteSpace($TargetManifest)) {
  foreach ($required in @($VideoInput, $CandidateManifest, $TargetManifest)) {
    if ([string]::IsNullOrWhiteSpace($required) -or -not (Test-Path -LiteralPath $required -PathType Leaf)) {
      throw "Candidate-bound quality mode requires existing input, candidate manifest and target manifest."
    }
  }
  if ([string]::IsNullOrWhiteSpace($OutputRoot)) {
    throw 'Candidate-bound quality mode requires -OutputRoot.'
  }
  New-Item -ItemType Directory -Path $OutputRoot -Force | Out-Null
  $qualityOutput = Join-Path $OutputRoot 'quality-report.json'
  $arguments = @(
    (Join-Path $repoRoot 'scripts\quality_candidate_acceptance.py'),
    '--candidate-manifest', $CandidateManifest,
    '--input', $VideoInput,
    '--target-manifest', $TargetManifest,
    '--output', $qualityOutput
  )
  if (-not [string]::IsNullOrWhiteSpace($FfmpegDir)) {
    $arguments += @('--ffmpeg-dir', $FfmpegDir)
  }
  & $python @arguments
  exit $LASTEXITCODE
}

& $python -m pytest tests/contract tests/unit/effects tests/unit/domain tests/unit/cache tests/unit/video -q
if ($LASTEXITCODE -ne 0) { throw 'Python unit/contract gates failed' }

& $python -m pytest tests/integration/test_project_api.py tests/integration/test_video_preview_routes.py tests/integration/test_video_render_routes.py -q
if ($LASTEXITCODE -ne 0) { throw 'Python integration gates failed' }

  Push-Location remotion
  try {
    & $remotionVitest run
    if ($LASTEXITCODE -ne 0) { throw 'Remotion tests failed' }
  }
  finally {
    Pop-Location
  }

& $tsc -p remotion/tsconfig.json --noEmit
if ($LASTEXITCODE -ne 0) { throw 'Remotion typecheck failed' }
& $tsc -p apps/web/tsconfig.json --noEmit
if ($LASTEXITCODE -ne 0) { throw 'Web typecheck failed' }

  Write-Output 'Effect Engine V2 quality gates passed.'
}
finally {
  Pop-Location
}
