$root = (Resolve-Path (Join-Path $PSScriptRoot "../..")).Path
. (Join-Path $root "scripts/windows_effect_acceptance_lib.ps1")

Describe "acceptance isolation" {
    It "blocks a database outside the isolated workspace" {
        $install = Join-Path $TestDrive "install"
        $workspace = Join-Path $TestDrive "workspace"
        $production = Join-Path $TestDrive "production/workspace.db"
        $caught = $null
        try {
            Assert-AcceptanceIsolation -Root $root -InstallRoot $install -WorkspaceRoot $workspace -DatabasePath $production -ProductionDatabasePath $production
        } catch {
            $caught = $_.Exception
        }
        if ($null -eq $caught -or $caught.Message -notlike "*E_ISOLATION_DB*") {
            throw "Expected E_ISOLATION_DB, got: $($caught.Message)"
        }
    }

    It "accepts an isolated install and workspace" {
        $install = Join-Path $TestDrive "install"
        $workspace = Join-Path $TestDrive "workspace"
        $database = Join-Path $workspace "workspace.db"
        Assert-AcceptanceIsolation -Root $root -InstallRoot $install -WorkspaceRoot $workspace -DatabasePath $database -ProductionDatabasePath (Join-Path $TestDrive "production/workspace.db")
    }

    It "finds a free port without terminating an occupied process" {
        $listener = [Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback, 0)
        $listener.Start()
        try {
            $occupied = ([Net.IPEndPoint]$listener.LocalEndpoint).Port
            $free = Get-FreeAcceptancePort -StartPort $occupied -EndPort ($occupied + 20)
            if ($free -eq $occupied) {
                throw "The acceptance port probe returned the occupied port."
            }
            if (-not $listener.Server.IsBound) {
                throw "The occupied listener was terminated by the acceptance port probe."
            }
        }
        finally {
            $listener.Stop()
        }
    }

    It "rejects a port range when every port is unavailable" {
        $caught = $null
        try {
            Get-FreeAcceptancePort -StartPort 0 -EndPort 0
        } catch {
            $caught = $_.Exception
        }
        if ($null -eq $caught -or $caught.Message -notlike "*E_PORT_UNAVAILABLE*") {
            throw "Expected E_PORT_UNAVAILABLE, got: $($caught.Message)"
        }
    }

    It "stops only a process owned by the current batch" {
        $shell = Join-Path $PSHOME "pwsh.exe"
        if (-not (Test-Path -LiteralPath $shell)) {
            $shell = Join-Path $PSHOME "powershell.exe"
        }
        $process = Start-OwnedProcess -FilePath $shell -ArgumentList @("-NoLogo", "-NoProfile", "-Command", "Start-Sleep -Seconds 30")
        try {
            $caught = $null
            try {
                Stop-OwnedProcess -ProcessId $process.ProcessId -OwnerToken "wrong-token"
            } catch {
                $caught = $_.Exception
            }
            if ($null -eq $caught -or $caught.Message -notlike "*E_PROCESS_NOT_OWNED*") {
                throw "Expected E_PROCESS_NOT_OWNED, got: $($caught.Message)"
            }
            Stop-OwnedProcess -ProcessId $process.ProcessId -OwnerToken $process.OwnerToken
            if (Get-Process -Id $process.ProcessId -ErrorAction SilentlyContinue) {
                throw "The owned process was not stopped."
            }
        }
        finally {
            if (Get-Process -Id $process.ProcessId -ErrorAction SilentlyContinue) {
                Stop-OwnedProcess -ProcessId $process.ProcessId -OwnerToken $process.OwnerToken
            }
        }
    }

    It "writes a structured evidence record" {
        $path = Join-Path $TestDrive "evidence.jsonl"
        Write-EvidenceRecord -EvidencePath $path -Step "isolation" -Result "passed" -Details @{ database = "isolated" }
        $record = Get-Content -Raw -LiteralPath $path | ConvertFrom-Json
        if ($record.step -ne "isolation" -or $record.result -ne "passed" -or $record.details.database -ne "isolated") {
            throw "The evidence record did not preserve the expected structured fields."
        }
    }

    It "keeps the acceptance PowerShell scripts ASCII" {
        $files = @(
            (Join-Path $root "scripts/windows_effect_acceptance_lib.ps1"),
            (Join-Path $root "scripts/windows_effect_acceptance.ps1"),
            $PSCommandPath
        )
        foreach ($file in $files) {
            if (@([IO.File]::ReadAllBytes($file) | Where-Object { $_ -ge 128 }).Count -gt 0) {
                throw "Acceptance script is not ASCII-only: $file"
            }
        }
    }
}
