[CmdletBinding()]
param(
    [string]$RepositoryRoot = "",
    [string]$ReleaseRoot = "",
    [switch]$SkipAutomation
)

$ErrorActionPreference = "Stop"
$platformRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
if ([string]::IsNullOrWhiteSpace($RepositoryRoot)) {
    $RepositoryRoot = [string](Resolve-Path (Join-Path $platformRoot ".."))
}
else {
    $RepositoryRoot = [System.IO.Path]::GetFullPath($RepositoryRoot)
}
if ([string]::IsNullOrWhiteSpace($ReleaseRoot)) {
    $ReleaseRoot = Join-Path $RepositoryRoot "dist\release"
}
else {
    $ReleaseRoot = [System.IO.Path]::GetFullPath($ReleaseRoot)
}

$automationPassed = $false
$windowsPassed = $false
$acceptancePassed = $false
try {
    Push-Location $RepositoryRoot
    try {
        if (-not $SkipAutomation) {
            & ".\.venv\Scripts\python.exe" -m pytest -p no:cacheprovider `
                tests/unit/peripheral_s1 `
                tests/integration/test_s1_module_smoke.py `
                tests/acceptance/test_s1_p03_p12_end_to_end.py `
                tests/acceptance/test_s1_failure_matrix.py `
                tests/release/test_s1_runtime_manifest.py `
                tests/security/test_p06_secret_isolation.py `
                tests/security/test_p12_delivery_redaction.py -q
            if ($LASTEXITCODE -ne 0) {
                throw "S1 automation tests failed."
            }
        }
        $automationPassed = $true

        $manifestPath = Join-Path $ReleaseRoot "peripheral\runtime-manifest.json"
        $hashPath = Join-Path $ReleaseRoot "peripheral\runtime-hashes.json"
        if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
            throw "Packaged S1 runtime manifest is missing: $manifestPath"
        }
        if (-not (Test-Path -LiteralPath $hashPath -PathType Leaf)) {
            throw "Packaged S1 runtime hashes are missing: $hashPath"
        }
        $manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
        $moduleIds = @($manifest.bundled_modules)
        foreach ($moduleId in 3..12 | ForEach-Object { "P{0:D2}" -f $_ }) {
            if ($moduleId -notin $moduleIds) {
                throw "Packaged S1 module is missing from the manifest: $moduleId"
            }
        }
        foreach ($relativePath in $manifest.required_release_files) {
            $candidate = Join-Path $ReleaseRoot ([string]$relativePath)
            if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) {
                throw "Required S1 release runtime is missing: $relativePath"
            }
        }
        $windowsPassed = $true

        $evidencePath = $env:S1_ACCEPTANCE_EVIDENCE
        if (-not [string]::IsNullOrWhiteSpace($evidencePath) -and
            (Test-Path -LiteralPath $evidencePath -PathType Leaf)) {
            $evidence = Get-Content -LiteralPath $evidencePath -Raw | ConvertFrom-Json
            $requiredEvidence = @(
                "windows_10_or_11",
                "chinese_path",
                "office_or_libreoffice",
                "ocr",
                "asr",
                "ffmpeg_remotion",
                "real_heygen",
                "manual_av_signoff",
                "rollback"
            )
            $passedEvidence = @($evidence.passed)
            $acceptancePassed = -not @($requiredEvidence | Where-Object { $_ -notin $passedEvidence })
        }
    }
    finally {
        Pop-Location
    }
}
finally {
    Write-Output ("S1_AUTOMATION=" + $(if ($automationPassed) { "PASS" } else { "BLOCK" }))
    Write-Output ("S1_WINDOWS=" + $(if ($windowsPassed) { "PASS" } else { "BLOCK" }))
    Write-Output ("S1_ACCEPTANCE=" + $(if ($acceptancePassed) { "PASS" } else { "BLOCK" }))
}

if (-not ($automationPassed -and $windowsPassed -and $acceptancePassed)) {
    exit 1
}
