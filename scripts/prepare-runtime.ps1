[CmdletBinding()]
param(
    [string]$Output = "runtime-assets",
    [string]$NodeExecutable,
    [string]$FfmpegExecutable,
    [string]$FfprobeExecutable,
    [string]$PnpmExecutable
)

$ErrorActionPreference = "Stop"
$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$runtimeRoot = Join-Path $repoRoot $Output

function Resolve-ToolPath {
    param(
        [string]$ConfiguredPath,
        [string]$CommandName,
        [string]$Description
    )

    if (-not [string]::IsNullOrWhiteSpace($ConfiguredPath)) {
        if (-not (Test-Path -LiteralPath $ConfiguredPath -PathType Leaf)) {
            throw "$Description was not found: $ConfiguredPath"
        }
        return (Resolve-Path -LiteralPath $ConfiguredPath).Path
    }
    $command = Get-Command $CommandName -ErrorAction SilentlyContinue
    if ($null -eq $command) {
        throw "$Description was not found. Pass -$Description with an explicit path."
    }
    $commandPath = [string]$command.Path
    if ([string]::IsNullOrWhiteSpace($commandPath)) {
        $commandPath = [string]$command.Source
    }
    if ([string]::IsNullOrWhiteSpace($commandPath) -or -not (Test-Path -LiteralPath $commandPath -PathType Leaf)) {
        throw "$Description was not found. Pass -$Description with an explicit path."
    }
    return (Resolve-Path -LiteralPath $commandPath).Path
}

function Stage-Executable {
    param(
        [string]$SourceExecutable,
        [string]$Destination
    )

    $destinationDirectory = Split-Path -Parent $Destination
    New-Item -ItemType Directory -Path $destinationDirectory -Force | Out-Null
    Copy-Item -LiteralPath $SourceExecutable -Destination $Destination -Force
    if (-not (Test-Path -LiteralPath $Destination -PathType Leaf)) {
        throw "Could not stage runtime executable: $Destination"
    }
}

function Stage-MediaRuntimeDependencies {
    param(
        [string[]]$SourceExecutables,
        [string]$DestinationDirectory
    )

    $sourceDirectories = @(
        $SourceExecutables |
            ForEach-Object { Split-Path -Parent $_ } |
            Select-Object -Unique
    )
    foreach ($mediaSourceDirectory in $sourceDirectories) {
        $runtimeLibraries = @(
            Get-ChildItem -LiteralPath $mediaSourceDirectory -Filter "*.dll" -File -ErrorAction SilentlyContinue
        )
        foreach ($runtimeLibrary in $runtimeLibraries) {
            Copy-Item -LiteralPath $runtimeLibrary.FullName -Destination $DestinationDirectory -Force
        }
    }
}

function Assert-ToolIdentity {
    param(
        [string]$Executable,
        [string]$ExpectedName,
        [string]$Description
    )

    $versionOutput = @(& $Executable -version 2>&1)
    $exitCode = $LASTEXITCODE
    $firstLine = if ($versionOutput.Count -gt 0) { [string]$versionOutput[0] } else { "" }
    $expectedPrefix = "$ExpectedName version"
    if (
        $exitCode -ne 0 -or
        -not $firstLine.StartsWith($expectedPrefix, [StringComparison]::OrdinalIgnoreCase)
    ) {
        throw "$Description is not an $ExpectedName executable: $Executable"
    }
}

$node = Resolve-ToolPath -ConfiguredPath $NodeExecutable -CommandName "node.exe" -Description "NodeExecutable"
$ffmpeg = Resolve-ToolPath -ConfiguredPath $FfmpegExecutable -CommandName "ffmpeg.exe" -Description "FfmpegExecutable"
$ffprobe = Resolve-ToolPath -ConfiguredPath $FfprobeExecutable -CommandName "ffprobe.exe" -Description "FfprobeExecutable"
$pnpm = Resolve-ToolPath -ConfiguredPath $PnpmExecutable -CommandName "pnpm.cmd" -Description "PnpmExecutable"

Assert-ToolIdentity -Executable $ffmpeg -ExpectedName "ffmpeg" -Description "FfmpegExecutable"
Assert-ToolIdentity -Executable $ffprobe -ExpectedName "ffprobe" -Description "FfprobeExecutable"

if (Test-Path -LiteralPath $runtimeRoot) {
    Remove-Item -LiteralPath $runtimeRoot -Recurse -Force
}
New-Item -ItemType Directory -Path $runtimeRoot -Force | Out-Null

Stage-Executable -SourceExecutable $node -Destination (Join-Path $runtimeRoot "node\node.exe")
Stage-Executable -SourceExecutable $ffmpeg -Destination (Join-Path $runtimeRoot "ffmpeg\ffmpeg.exe")
Stage-Executable -SourceExecutable $ffprobe -Destination (Join-Path $runtimeRoot "ffmpeg\ffprobe.exe")
Stage-MediaRuntimeDependencies `
    -SourceExecutables @($ffmpeg, $ffprobe) `
    -DestinationDirectory (Join-Path $runtimeRoot "ffmpeg")

$remotionRuntime = Join-Path $runtimeRoot "remotion"
& $pnpm `
    --config.node-linker=hoisted `
    --config.inject-workspace-packages=true `
    --filter "@workbench/remotion" `
    deploy --prod $remotionRuntime
if ($LASTEXITCODE -ne 0) {
    throw "pnpm deploy failed while preparing the Remotion runtime."
}
$pnpmVirtualStore = Join-Path $remotionRuntime "node_modules\.pnpm"
$virtualPackageDirectories = @(
    Get-ChildItem -LiteralPath $pnpmVirtualStore -Directory -ErrorAction SilentlyContinue
)
if ($virtualPackageDirectories.Count -gt 0) {
    throw "Prepared Remotion runtime contains virtual package directories; use the flat layout for Windows installers."
}
Copy-Item -LiteralPath (Join-Path $repoRoot "remotion\src") -Destination $remotionRuntime -Recurse -Force

$required = @(
    "node\node.exe",
    "ffmpeg\ffmpeg.exe",
    "ffmpeg\ffprobe.exe",
    "remotion\node_modules\@remotion\cli\remotion-cli.js",
    "remotion\src\index.ts"
)
foreach ($relativePath in $required) {
    $path = Join-Path $runtimeRoot $relativePath
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Prepared runtime is missing: $relativePath"
    }
}
Write-Output "Prepared rendering runtime: $runtimeRoot"
