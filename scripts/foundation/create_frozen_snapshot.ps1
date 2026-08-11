[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$RepositoryPath,
    [Parameter(Mandatory = $true)][string]$Checkpoint,
    [Parameter(Mandatory = $true)][string]$OutputPath,
    [string[]]$OverlayPaths = @()
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

function Get-RelativePath {
    param([string]$Root, [string]$Path)
    return $Path.Substring($Root.Length + 1).Replace('\', '/')
}

$repoFull = (Resolve-Path -LiteralPath $RepositoryPath).Path.TrimEnd('\')
$outputFull = [IO.Path]::GetFullPath($OutputPath)
if ($outputFull.StartsWith("$repoFull\", [StringComparison]::OrdinalIgnoreCase)) {
    throw 'frozen snapshot must not be created inside the source repository'
}
if (Test-Path -LiteralPath $outputFull) {
    throw "snapshot output already exists and will not be overwritten: $outputFull"
}

Get-GitText -Arguments @('cat-file', '-e', "$Checkpoint^{commit}") | Out-Null
$checkpointHead = Get-GitText -Arguments @('rev-parse', "$Checkpoint^{commit}")
New-Item -ItemType Directory -Path $outputFull -Force | Out-Null
$archivePath = Join-Path ([IO.Path]::GetTempPath()) ("foundation-$checkpointHead-$([Guid]::NewGuid()).zip")
$completed = $false

try {
    & git -C $RepositoryPath archive --format=zip "--output=$archivePath" $Checkpoint
    if ($LASTEXITCODE -ne 0) {
        throw "unable to archive checkpoint $Checkpoint"
    }
    Expand-Archive -LiteralPath $archivePath -DestinationPath $outputFull -Force

    $normalizedOverlayPaths = @()
    foreach ($overlay in $OverlayPaths) {
        $relative = $overlay.Replace('\', '/').TrimStart('/')
        if ($relative -match '(^|/)\.\.?(/|$)' -or [IO.Path]::IsPathRooted($relative)) {
            throw "overlay path must be repository-relative: $overlay"
        }
        $source = Join-Path $repoFull ($relative.Replace('/', '\'))
        if (-not (Test-Path -LiteralPath $source -PathType Leaf)) {
            throw "overlay file does not exist: $overlay"
        }
        $target = Join-Path $outputFull ($relative.Replace('/', '\'))
        New-Item -ItemType Directory -Path (Split-Path -Parent $target) -Force | Out-Null
        Copy-Item -LiteralPath $source -Destination $target -Force
        $normalizedOverlayPaths += $relative
    }

    $overlayText = Get-GitText -Arguments (@('diff', '--binary', $Checkpoint, '--') + $normalizedOverlayPaths)
    $overlayDirectory = Join-Path $outputFull 'foundation-overlays'
    New-Item -ItemType Directory -Path $overlayDirectory -Force | Out-Null
    $overlayFile = Join-Path $overlayDirectory 'working-tree.patch'
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [IO.File]::WriteAllText($overlayFile, $overlayText + "`n", $utf8NoBom)

    $records = @()
    $outputRoot = $outputFull.TrimEnd('\')
    foreach ($file in Get-ChildItem -LiteralPath $outputFull -Recurse -File | Sort-Object FullName) {
        $relative = Get-RelativePath -Root $outputRoot -Path $file.FullName
        if ($relative -eq 'manifest.json') {
            continue
        }
        $records += [ordered]@{
            path = $relative
            size = $file.Length
            sha256 = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
        }
    }

    $manifestCore = [ordered]@{
        schema_version = '1.0'
        checkpoint = $Checkpoint
        checkpoint_head = $checkpointHead
        overlay_paths = $normalizedOverlayPaths
        overlay_patch_sha256 = (Get-FileHash -LiteralPath $overlayFile -Algorithm SHA256).Hash.ToLowerInvariant()
        files = $records
    }
    $coreJson = $manifestCore | ConvertTo-Json -Depth 10 -Compress
    $manifest = [ordered]@{}
    foreach ($property in $manifestCore.Keys) {
        $manifest[$property] = $manifestCore[$property]
    }
    $manifest['manifest_sha256'] = Get-Sha256Text -Value $coreJson
    [IO.File]::WriteAllText((Join-Path $outputFull 'manifest.json'), ($manifest | ConvertTo-Json -Depth 10), $utf8NoBom)
    $completed = $true
    [pscustomobject]@{
        output = $outputFull
        checkpoint = $Checkpoint
        checkpoint_head = $checkpointHead
        overlay_count = $normalizedOverlayPaths.Count
        file_count = $records.Count
        manifest_sha256 = $manifest['manifest_sha256']
    } | ConvertTo-Json -Compress
}
finally {
    Remove-Item -LiteralPath $archivePath -Force -ErrorAction SilentlyContinue
    if (-not $completed -and (Test-Path -LiteralPath $outputFull)) {
        Remove-Item -LiteralPath $outputFull -Recurse -Force -ErrorAction SilentlyContinue
    }
}
