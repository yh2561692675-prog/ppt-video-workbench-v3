[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$CandidateId,
    [string]$EvidenceRoot = "test-results\web-release"
)

$ErrorActionPreference = "Stop"
$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$reportRoot = Join-Path $repoRoot $EvidenceRoot
$runRoot = Join-Path $reportRoot $CandidateId
New-Item -ItemType Directory -Path $runRoot -Force | Out-Null

function Invoke-WebGate {
    param(
        [string]$Name,
        [string[]]$Arguments
    )

    $stdoutPath = Join-Path $runRoot "$Name.stdout.log"
    $stderrPath = Join-Path $runRoot "$Name.stderr.log"
    Push-Location $repoRoot
    $previousErrorActionPreference = $ErrorActionPreference
    try {
        # pnpm writes its command echo to stderr even after a successful run.
        # Do not let PowerShell promote that native stderr line to a terminating
        # error; the process exit code remains the authoritative result.
        $ErrorActionPreference = "Continue"
        & pnpm.cmd @Arguments 1> $stdoutPath 2> $stderrPath
        $exitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousErrorActionPreference
        Pop-Location
    }
    if ($exitCode -ne 0) {
        throw "Web release gate failed: $Name. stdout=$stdoutPath stderr=$stderrPath"
    }
    return [ordered]@{
        name = $Name
        exit_code = $exitCode
        stdout = $stdoutPath
        stderr = $stderrPath
    }
}

$results = @()
$results += Invoke-WebGate -Name "full-web-test" -Arguments @(
    "--filter",
    "@workbench/web",
    "test",
    "--reporter=verbose"
)
$scenarioIndex = 0
foreach ($name in @(
    "immediately disables HeyGen after local import even while project refetch remains stale",
    "disables local import when a HeyGen batch starts and keeps it disabled after success",
    "restores the HeyGen route from completed page audio after a project reload"
)) {
    $scenarioIndex++
    for ($attempt = 1; $attempt -le 3; $attempt++) {
        $slug = "workflow-$scenarioIndex-$attempt"
        $results += Invoke-WebGate -Name $slug -Arguments @(
            "--filter",
            "@workbench/web",
            "test",
            "src/features/workflow/WorkflowShell.test.tsx",
            "--testNamePattern",
            $name
        )
    }
}
$results += Invoke-WebGate -Name "web-typecheck" -Arguments @(
    "--filter",
    "@workbench/web",
    "typecheck"
)
$results += Invoke-WebGate -Name "web-build" -Arguments @(
    "--filter",
    "@workbench/web",
    "build",
    "--outDir",
    (Join-Path $runRoot "web-build-dist")
)

[ordered]@{
    schema_version = "1.0"
    candidate_id = $CandidateId
    result = "passed"
    commands = $results
} | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $runRoot "web-release-gate.json") -Encoding UTF8

Write-Output "WEB_RELEASE_GATE=PASS candidate_id=$CandidateId"
