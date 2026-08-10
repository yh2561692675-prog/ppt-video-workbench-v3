$script:OwnedProcesses = @{}

function ConvertTo-NormalizedAcceptancePath {
  param(
    [Parameter(Mandatory = $true)]
    [string]$Path
  )

  if ([string]::IsNullOrWhiteSpace($Path)) {
    throw "E_ISOLATION_PATH: path is required"
  }

  return [IO.Path]::GetFullPath($Path).TrimEnd('\', '/')
}

function Test-AcceptancePathWithin {
  param(
    [Parameter(Mandatory = $true)]
    [string]$Candidate,
    [Parameter(Mandatory = $true)]
    [string]$Parent
  )

  $candidatePath = ConvertTo-NormalizedAcceptancePath $Candidate
  $parentPath = ConvertTo-NormalizedAcceptancePath $Parent
  return $candidatePath.Equals($parentPath, [StringComparison]::OrdinalIgnoreCase) -or
    $candidatePath.StartsWith($parentPath + '\', [StringComparison]::OrdinalIgnoreCase)
}

function Assert-AcceptanceIsolation {
  param(
    [Parameter(Mandatory = $true)]
    [string]$Root,
    [Parameter(Mandatory = $true)]
    [string]$InstallRoot,
    [Parameter(Mandatory = $true)]
    [string]$WorkspaceRoot,
    [Parameter(Mandatory = $true)]
    [string]$DatabasePath,
    [string]$ProductionDatabasePath = ""
  )

  $rootPath = ConvertTo-NormalizedAcceptancePath $Root
  $installPath = ConvertTo-NormalizedAcceptancePath $InstallRoot
  $workspacePath = ConvertTo-NormalizedAcceptancePath $WorkspaceRoot
  $databasePath = ConvertTo-NormalizedAcceptancePath $DatabasePath
  $productionPath = if ([string]::IsNullOrWhiteSpace($ProductionDatabasePath)) {
    ""
  } else {
    ConvertTo-NormalizedAcceptancePath $ProductionDatabasePath
  }

  if (
    (Test-AcceptancePathWithin $installPath $rootPath) -or
    (Test-AcceptancePathWithin $workspacePath $rootPath)
  ) {
    throw "E_ISOLATION_ROOT: acceptance roots must be outside the source root"
  }
  if (
    (Test-AcceptancePathWithin $installPath $workspacePath) -or
    (Test-AcceptancePathWithin $workspacePath $installPath)
  ) {
    throw "E_ISOLATION_ROOT: install and workspace roots must be separate"
  }
  if (-not (Test-AcceptancePathWithin $databasePath $workspacePath)) {
    throw "E_ISOLATION_DB: database must be inside the isolated workspace"
  }
  if ($productionPath -and $databasePath.Equals($productionPath, [StringComparison]::OrdinalIgnoreCase)) {
    throw "E_ISOLATION_DB: production database path is forbidden"
  }

  return [pscustomobject]@{
    root = $rootPath
    install_root = $installPath
    workspace_root = $workspacePath
    database_path = $databasePath
    production_database_path = $productionPath
    result = "passed"
  }
}

function Get-FreeAcceptancePort {
  param(
    [int]$StartPort = 49152,
    [int]$EndPort = 49252
  )

  if ($StartPort -lt 1024 -or $EndPort -lt $StartPort -or $EndPort -gt 65535) {
    throw "E_PORT_UNAVAILABLE: invalid acceptance port range"
  }

  for ($port = $StartPort; $port -le $EndPort; $port++) {
    $listener = [Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback, $port)
    try {
      $listener.Start()
      return $port
    } catch {
      continue
    } finally {
      $listener.Stop()
    }
  }

  throw "E_PORT_UNAVAILABLE: no free acceptance port"
}

function Start-OwnedProcess {
  param(
    [Parameter(Mandatory = $true)]
    [string]$FilePath,
    [string[]]$ArgumentList = @(),
    [string]$WorkingDirectory = ""
  )

  $parameters = @{
    FilePath = $FilePath
    ArgumentList = $ArgumentList
    PassThru = $true
  }
  if (-not [string]::IsNullOrWhiteSpace($WorkingDirectory)) {
    $parameters.WorkingDirectory = $WorkingDirectory
  }

  $process = Start-Process @parameters
  $ownerToken = [guid]::NewGuid().ToString("N")
  $script:OwnedProcesses[$ownerToken] = $process.Id
  return [pscustomobject]@{
    ProcessId = $process.Id
    OwnerToken = $ownerToken
    Process = $process
  }
}

function Stop-OwnedProcess {
  param(
    [Parameter(Mandatory = $true)]
    [int]$ProcessId,
    [Parameter(Mandatory = $true)]
    [string]$OwnerToken
  )

  if (-not $script:OwnedProcesses.ContainsKey($OwnerToken) -or $script:OwnedProcesses[$OwnerToken] -ne $ProcessId) {
    throw "E_PROCESS_NOT_OWNED: process is not owned by this acceptance batch"
  }

  $process = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
  if ($process) {
    Stop-Process -Id $ProcessId -Force -ErrorAction Stop
    $process.WaitForExit(5000)
  }
  $script:OwnedProcesses.Remove($OwnerToken)
  return $true
}

function Write-EvidenceRecord {
  param(
    [Parameter(Mandatory = $true)]
    [string]$EvidencePath,
    [Parameter(Mandatory = $true)]
    [string]$Step,
    [Parameter(Mandatory = $true)]
    [string]$Result,
    [hashtable]$Details = @{}
  )

  $parent = Split-Path -Parent $EvidencePath
  if ($parent) {
    New-Item -ItemType Directory -Path $parent -Force | Out-Null
  }
  $record = [ordered]@{
    timestamp_utc = [DateTime]::UtcNow.ToString("o")
    step = $Step
    result = $Result
    details = $Details
  }
  $json = $record | ConvertTo-Json -Compress -Depth 12
  $utf8 = [Text.UTF8Encoding]::new($false)
  [IO.File]::AppendAllText($EvidencePath, $json + [Environment]::NewLine, $utf8)
}
