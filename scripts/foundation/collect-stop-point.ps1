[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$WindowId,
    [Parameter(Mandatory = $true)][string]$TaskName,
    [ValidateSet('writer', 'read_only', 'idle')][string]$Mode = 'idle',
    [Parameter(Mandatory = $true)][string]$RepositoryPath,
    [string[]]$OwnedPaths = @(),
    [string[]]$SharedPathsTouched = @(),
    [string[]]$Completed = @(),
    [string[]]$Remaining = @(),
    [string[]]$EvidenceRefs = @(),
    [switch]$WillWriteAgain,
    [Parameter(Mandatory = $true)][string]$SafeResume,
    [Parameter(Mandatory = $true)][string]$OutputPath
)

$ErrorActionPreference = 'Stop'

function Assert-LogicalPath {
    param([string]$Value)
    $normalized = $Value.Replace('\', '/')
    if ([IO.Path]::IsPathRooted($normalized) -or $normalized -match '^[A-Za-z]:') {
        throw "absolute path is not allowed in stop point: $Value"
    }
    if ($normalized -match '(^|/)\.\.?(/|$)' -or [string]::IsNullOrWhiteSpace($normalized)) {
        throw "path escape or empty path is not allowed: $Value"
    }
    return $normalized
}

function Get-GitText {
    param([string[]]$Arguments)
    $stderrPath = Join-Path ([IO.Path]::GetTempPath()) ("foundation-git-$PID-$([Guid]::NewGuid()).stderr")
    try {
        $previousErrorAction = $ErrorActionPreference
        $ErrorActionPreference = 'Continue'
        try {
            $value = & git -C $RepositoryPath @Arguments 2> $stderrPath | Out-String
            $exitCode = $LASTEXITCODE
        }
        finally {
            $ErrorActionPreference = $previousErrorAction
        }
        $stderr = if (Test-Path -LiteralPath $stderrPath) {
            Get-Content -LiteralPath $stderrPath -Raw -ErrorAction SilentlyContinue
        }
        if ($stderr) {
            Write-Warning ("git stderr: " + $stderr.Trim())
        }
        if ($exitCode -ne 0) {
            throw "git command failed: git -C $RepositoryPath $($Arguments -join ' ')"
        }
        return $value.Trim()
    }
    finally {
        Remove-Item -LiteralPath $stderrPath -Force -ErrorAction SilentlyContinue
    }
}

function Get-Sha256Text {
    param([string]$Value)
    $bytes = [Text.Encoding]::UTF8.GetBytes($Value)
    $hash = [Security.Cryptography.SHA256]::Create()
    try {
        return ([BitConverter]::ToString($hash.ComputeHash($bytes))).Replace('-', '').ToLowerInvariant()
    }
    finally {
        $hash.Dispose()
    }
}

$repoFull = (Resolve-Path -LiteralPath $RepositoryPath).Path.TrimEnd('\')
$outputFull = [IO.Path]::GetFullPath($OutputPath)
if (-not $outputFull.StartsWith("$repoFull\", [StringComparison]::OrdinalIgnoreCase)) {
    throw 'stop point output must remain inside the repository boundary'
}

$status = Get-GitText -Arguments @('status', '--porcelain=v2', '--untracked-files=all')
$branch = Get-GitText -Arguments @('branch', '--show-current')
$head = Get-GitText -Arguments @('rev-parse', 'HEAD')
$parent = Split-Path -Parent $outputFull
New-Item -ItemType Directory -Path $parent -Force | Out-Null

$payload = [ordered]@{
    schema_version = '1.0'
    window_id = $WindowId
    task_name = $TaskName
    mode = $Mode
    repository = [ordered]@{
        path = 'source-root'
        branch = $branch
        head = $head
        status_manifest_sha256 = Get-Sha256Text -Value $status
    }
    owned_paths = @($OwnedPaths | ForEach-Object { Assert-LogicalPath $_ })
    shared_paths_touched = @($SharedPathsTouched | ForEach-Object { Assert-LogicalPath $_ })
    completed = @($Completed)
    remaining = @($Remaining)
    evidence_refs = @($EvidenceRefs | ForEach-Object { Assert-LogicalPath $_ })
    will_write_again = [bool]$WillWriteAgain
    safe_resume = $SafeResume
}

$json = $payload | ConvertTo-Json -Depth 8
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[IO.File]::WriteAllText($outputFull, $json, $utf8NoBom)
Write-Output $outputFull
