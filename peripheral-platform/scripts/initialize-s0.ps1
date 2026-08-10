[CmdletBinding()]
param(
    [string]$WorkspaceRoot = $(
        if ([string]::IsNullOrWhiteSpace($env:WORKBENCH_WORKSPACE)) { "F:\Video" }
        else { $env:WORKBENCH_WORKSPACE }
    ),
    [long]$MinimumFreeBytes = 5GB
)

$ErrorActionPreference = "Stop"
$results = [ordered]@{
    workspace_is_not_drive_root = $false
    drive_has_minimum_free_space = $false
    directories_ready = $false
    existing_database_preserved = $false
}
$exitCode = 0

try {
    if ([string]::IsNullOrWhiteSpace($WorkspaceRoot)) {
        throw "WorkspaceRoot must not be empty."
    }
    $fullWorkspace = [System.IO.Path]::GetFullPath($WorkspaceRoot)
    $driveRoot = [System.IO.Path]::GetPathRoot($fullWorkspace)
    if ([string]::IsNullOrWhiteSpace($driveRoot)) {
        throw "WorkspaceRoot must be an absolute local path."
    }
    $normalizedWorkspace = $fullWorkspace.TrimEnd("\", "/")
    $normalizedDrive = $driveRoot.TrimEnd("\", "/")
    if ($normalizedWorkspace -eq $normalizedDrive) {
        throw "WorkspaceRoot must not be a drive root."
    }
    $results.workspace_is_not_drive_root = $true

    $drive = [System.IO.DriveInfo]::new($driveRoot)
    if (-not $drive.IsReady -or $drive.AvailableFreeSpace -lt $MinimumFreeBytes) {
        throw "Workspace drive must have at least 5GB free."
    }
    $results.drive_has_minimum_free_space = $true

    $databasePath = Join-Path $fullWorkspace "workspace-data\peripheral.db"
    $databaseExisted = Test-Path -LiteralPath $databasePath -PathType Leaf
    $directories = @(
        "workspace-data",
        "projects",
        "cache",
        "logs",
        "diagnostics",
        "backups",
        "quarantine"
    )
    foreach ($relativePath in $directories) {
        New-Item -ItemType Directory -Path (Join-Path $fullWorkspace $relativePath) -Force |
            Out-Null
    }
    $results.directories_ready = $true
    $results.existing_database_preserved = (
        (-not $databaseExisted) -or (Test-Path -LiteralPath $databasePath -PathType Leaf)
    )
}
catch {
    $exitCode = 1
    $results["error"] = $_.Exception.Message
}

$results["workspace_root"] = if ($fullWorkspace) { $fullWorkspace } else { $WorkspaceRoot }
$results | ConvertTo-Json -Compress
exit $exitCode
