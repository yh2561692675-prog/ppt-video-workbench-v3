[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$platformRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$repoRoot = Resolve-Path (Join-Path $platformRoot "..")
$verifyWorkspace = Join-Path $env:TEMP "PPTVideoWorkbench-S0-Verify"
$releaseRoot = Join-Path $repoRoot "dist\release"

function Invoke-CheckedStep {
    param(
        [string]$Name,
        [scriptblock]$Command
    )
    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "$Name failed with exit code $LASTEXITCODE."
    }
    Write-Output "$Name=PASS"
}

function Test-PackageHashes {
    $hashManifestPath = Join-Path $releaseRoot "peripheral\runtime-hashes.json"
    if (-not (Test-Path -LiteralPath $hashManifestPath -PathType Leaf)) {
        throw "Peripheral runtime hash manifest was not found."
    }
    $hashManifest = Get-Content -LiteralPath $hashManifestPath -Raw | ConvertFrom-Json
    foreach ($entry in $hashManifest.files) {
        $path = Join-Path $releaseRoot ([string]$entry.relative_path)
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
            throw "Manifest file was not found: $($entry.relative_path)"
        }
        $actual = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($actual -ne [string]$entry.sha256) {
            throw "Manifest hash mismatch: $($entry.relative_path)"
        }
    }
}

Push-Location $repoRoot
try {
    Invoke-CheckedStep -Name "UNIT_TESTS" -Command {
        python -m pytest peripheral-platform/tests/unit -v
    }
    Invoke-CheckedStep -Name "CONTRACT_TESTS" -Command {
        python -m pytest peripheral-platform/tests/contract -v
    }
    Invoke-CheckedStep -Name "SECURITY_TESTS" -Command {
        python -m pytest peripheral-platform/tests/security -v
    }
    Invoke-CheckedStep -Name "INTEGRATION_TESTS" -Command {
        python -m pytest peripheral-platform/tests/integration -v
    }
    Invoke-CheckedStep -Name "COMPILEALL" -Command {
        python -m compileall -q peripheral-platform/src
    }
    Invoke-CheckedStep -Name "WINDOWS_BUILD" -Command {
        & ".\peripheral-platform\scripts\build-s0.ps1"
    }
    Invoke-CheckedStep -Name "WINDOWS_SMOKE" -Command {
        & ".\peripheral-platform\scripts\smoke-s0.ps1" `
            -WorkspaceRoot $verifyWorkspace
    }

    $databasePath = Join-Path $verifyWorkspace "workspace-data\peripheral.db"
    & python -c "import sqlite3,sys; c=sqlite3.connect(sys.argv[1]); q=c.execute('PRAGMA quick_check').fetchone()[0]; f=len(c.execute('PRAGMA foreign_key_check').fetchall()); print(f'DATABASE_QUICK_CHECK={q}'); print(f'DATABASE_FOREIGN_KEY_ERRORS={f}'); raise SystemExit(0 if q=='ok' and f==0 else 1)" $databasePath
    if ($LASTEXITCODE -ne 0) {
        throw "Database integrity verification failed."
    }
    Test-PackageHashes
    Write-Output "PACKAGE_MANIFEST=PASS"
    Write-Output "S0_ACCEPTANCE=PASS"
}
finally {
    Pop-Location
}
