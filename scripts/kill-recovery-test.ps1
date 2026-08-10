param(
    [string]$PythonRunner = "uv"
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot ".."))
Push-Location $repoRoot
try {
    & $PythonRunner run pytest tests/unit/jobs/test_checkpoint.py tests/integration/test_crash_recovery_matrix.py -q
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}
finally {
    Pop-Location
}
