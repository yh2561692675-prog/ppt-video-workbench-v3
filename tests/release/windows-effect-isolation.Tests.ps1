BeforeAll {
    $root = (Resolve-Path (Join-Path $PSScriptRoot "../..")).Path
    . (Join-Path $root "scripts/windows_effect_acceptance_lib.ps1")
}

Describe "acceptance isolation" {
    It "blocks a database outside the isolated workspace" {
        $install = Join-Path $TestDrive "install"
        $workspace = Join-Path $TestDrive "workspace"
        $production = Join-Path $TestDrive "production/workspace.db"
        { Assert-AcceptanceIsolation -Root $root -InstallRoot $install -WorkspaceRoot $workspace -DatabasePath $production -ProductionDatabasePath $production } |
            Should -Throw "*E_ISOLATION_DB*"
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
            $free = Get-FreeAcceptancePort -StartPort $occupied -EndPort ($occupied + 2)
            $free | Should -Not -Be $occupied
            $listener.Server.IsBound | Should -BeTrue
        }
        finally {
            $listener.Stop()
        }
    }

    It "rejects a port range when every port is unavailable" {
        { Get-FreeAcceptancePort -StartPort 0 -EndPort 0 } |
            Should -Throw "*E_PORT_UNAVAILABLE*"
    }

    It "stops only a process owned by the current batch" {
        $shell = Join-Path $PSHOME "pwsh.exe"
        if (-not (Test-Path -LiteralPath $shell)) {
            $shell = Join-Path $PSHOME "powershell.exe"
        }
        $process = Start-OwnedProcess -FilePath $shell -ArgumentList @("-NoLogo", "-NoProfile", "-Command", "Start-Sleep -Seconds 30")
        try {
            { Stop-OwnedProcess -ProcessId $process.ProcessId -OwnerToken "wrong-token" } |
                Should -Throw "*E_PROCESS_NOT_OWNED*"
            Stop-OwnedProcess -ProcessId $process.ProcessId -OwnerToken $process.OwnerToken
            (Get-Process -Id $process.ProcessId -ErrorAction SilentlyContinue) | Should -BeNullOrEmpty
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
        $record.step | Should -Be "isolation"
        $record.result | Should -Be "passed"
        $record.details.database | Should -Be "isolated"
    }

    It "keeps the acceptance PowerShell scripts ASCII" {
        $files = @(
            (Join-Path $root "scripts/windows_effect_acceptance_lib.ps1"),
            (Join-Path $root "scripts/windows_effect_acceptance.ps1"),
            $PSCommandPath
        )
        foreach ($file in $files) {
            [IO.File]::ReadAllBytes($file) | Where-Object { $_ -ge 128 } | Should -BeNullOrEmpty
        }
    }
}
