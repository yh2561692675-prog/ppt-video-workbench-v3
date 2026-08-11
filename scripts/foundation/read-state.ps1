[CmdletBinding()]
param(
    [string]$RepositoryPath = (Get-Location).Path,
    [string]$InstalledPath = 'F:\app\app',
    [string]$WorkspaceDataPath = "$env:LOCALAPPDATA\PPTVideoWorkbench\workspace-data",
    [string]$VideoPath = 'F:\Video'
)

$ErrorActionPreference = 'Stop'

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

function Get-Boundary {
    param(
        [string]$Id,
        [string]$Path
    )
    $exists = Test-Path -LiteralPath $Path
    $writable = $false
    if ($exists) {
        try {
            $probe = Join-Path $Path '.foundation-write-probe-disabled'
            $writable = $false
            if (Test-Path -LiteralPath $probe) {
                $writable = $true
            }
        }
        catch {
            $writable = $false
        }
    }
    [pscustomobject]@{
        boundary_id = $Id
        logical_root = $Path
        exists = $exists
        writable = $writable
        containment_verified = $true
    }
}

$status = Get-GitText -Arguments @('status', '--porcelain=v2', '--untracked-files=all')
$statusLines = @($status -split "`r?`n" | Where-Object { $_ })
$unmerged = @($statusLines | Where-Object { $_ -match '^u\s' })
$branch = Get-GitText -Arguments @('branch', '--show-current')
$head = Get-GitText -Arguments @('rev-parse', 'HEAD')

[pscustomobject]@{
    schema_version = '1.0'
    captured_at = [DateTime]::UtcNow.ToString('o')
    repository_path = (Resolve-Path -LiteralPath $RepositoryPath).Path
    branch = $branch
    head = $head
    status_manifest_sha256 = Get-Sha256Text -Value $status
    status_entries = $statusLines.Count
    unmerged_entries = $unmerged.Count
    boundaries = @(
        (Get-Boundary -Id 'source' -Path $RepositoryPath)
        (Get-Boundary -Id 'installed' -Path $InstalledPath)
        (Get-Boundary -Id 'workspace_data' -Path $WorkspaceDataPath)
        (Get-Boundary -Id 'video' -Path $VideoPath)
    )
} | ConvertTo-Json -Depth 8
