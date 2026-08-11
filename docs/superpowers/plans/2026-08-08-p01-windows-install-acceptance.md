# P01 Windows Installation Acceptance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a repeatable Windows acceptance runner that proves an installer can install, start, restart, uninstall, and retain workspace data, producing a redacted JSON/HTML release decision.

**Architecture:** Python owns the report schema and redaction. PowerShell owns installer and process actions, writes phase evidence, and calls the Python CLI. A missing or failed phase blocks the release decision. The runner never deletes `F:\\Video`.

**Tech Stack:** Python 3.12 standard library, pytest, Windows PowerShell, Inno Setup.

## Global Constraints

- Only loopback endpoints (`http://127.0.0.1:`) are accepted.
- Reports retain phase result, hashes, and derived diagnostics but redact user paths and secrets.
- The default workspace is `F:\\Video`; P01 never deletes or modifies it.
- A `pass` requires `install`, `first_launch`, `restart`, `uninstall`, and `workspace_retention` all to pass.
- P01 does not modify S0 host behavior or video-production behavior.

---

### Task 1: Add the redacted, fail-closed acceptance-report contract

**Files:**

- Create: `scripts/windows_acceptance_report.py`
- Create: `tests/release/test_windows_acceptance_report.py`

**Interfaces:**

- Consumes: evidence object containing `release` and `phases`.
- Produces: `build_report(evidence: dict[str, object]) -> dict[str, object]` plus `acceptance-report.json` and `acceptance-report.html`.

- [x] **Step 1: Write failing tests**

```python
def test_report_passes_only_when_every_required_phase_passes() -> None:
    from scripts.windows_acceptance_report import build_report

    report = build_report(
        {
            "release": {"installer_sha256": "a" * 64},
            "phases": {name: {"result": "passed"} for name in REQUIRED_PHASES},
        }
    )
    assert report["decision"] == "pass"
    assert report["blocking_failures"] == []


def test_report_blocks_and_redacts_user_paths_and_tokens() -> None:
    from scripts.windows_acceptance_report import build_report

    report = build_report(
        {
            "token": "Bearer secret-value",
            "release": {"installer_path": r"C:\\Users\\HanYu\\setup.exe"},
            "phases": {},
        }
    )
    serialized = json.dumps(report)
    assert report["decision"] == "block"
    assert "HanYu" not in serialized
    assert "secret-value" not in serialized
```

- [x] **Step 2: Verify red**

Run `uv run pytest tests/release/test_windows_acceptance_report.py -v`. Expected: fail because the module does not exist.

- [x] **Step 3: Implement only the report contract**

```python
REQUIRED_PHASES = ("install", "first_launch", "restart", "uninstall", "workspace_retention")


def build_report(evidence: dict[str, object]) -> dict[str, object]:
    redacted = redact(evidence)
    phases = redacted.get("phases", {})
    failures = [name for name in REQUIRED_PHASES if phases.get(name, {}).get("result") != "passed"]
    return {
        "schema_version": "1.0",
        "decision": "pass" if not failures else "block",
        "blocking_failures": failures,
        "evidence": redacted,
    }
```

`redact` masks the keys `token`, `authorization`, `api_key`, `secret`, and `cookie`; changes `Bearer <value>` to `Bearer ***`; and changes `C:\\Users\\<name>` to `%USERPROFILE%`. The CLI accepts `--evidence` and `--output-dir`, writes escaped HTML, and exits zero only for a pass.

- [x] **Step 4: Verify green and commit**

Run `uv run pytest tests/release/test_windows_acceptance_report.py -v`. Expected: pass. Commit with `git add scripts/windows_acceptance_report.py tests/release/test_windows_acceptance_report.py && git commit -m "feat: add redacted Windows acceptance report"`.

### Task 2: Add the Windows install/start/restart/uninstall runner

**Files:**

- Create: `tests/release/windows-acceptance.ps1`
- Modify: `tests/release/test_launcher_contract.py`

**Interfaces:**

- Consumes: `-InstallerPath`, optional `-InstallRoot`, optional `-ReportDirectory`.
- Produces: `acceptance-evidence.json`, report files, and exactly one `P01_WINDOWS_ACCEPTANCE=PASS|BLOCK` marker.

- [x] **Step 1: Write a failing script-contract test**

```python
def test_windows_acceptance_runner_proves_start_restart_and_retention() -> None:
    source = (REPOSITORY_ROOT / "tests/release/windows-acceptance.ps1").read_text(encoding="utf-8")
    for text in (
        "Get-FileHash -Algorithm SHA256",
        "Start-Process",
        "endpoint.json",
        "first_launch",
        "restart",
        "workspace_retention",
        "P01_WINDOWS_ACCEPTANCE=PASS",
        "P01_WINDOWS_ACCEPTANCE=BLOCK",
        "F:\\Video",
    ):
        assert text in source
    assert "Remove-Item -LiteralPath $workspaceRoot" not in source
```

- [x] **Step 2: Verify red**

Run `uv run pytest tests/release/test_launcher_contract.py -v`. Expected: fail because the runner does not exist.

- [x] **Step 3: Implement only the runner**

```powershell
param(
  [Parameter(Mandatory = $true)][string]$InstallerPath,
  [string]$InstallRoot = (Join-Path $env:TEMP "PPTVideoWorkbench-P01"),
  [string]$ReportDirectory = (Join-Path $env:TEMP "PPTVideoWorkbench-P01-Report")
)
```

Hash the installer; write `%LOCALAPPDATA%\\PPTVideoWorkbench\\workspace-data\\p01-retention.json` and retain its hash; install silently; require `launcher.ps1`; run launcher twice with `-NoBrowser` and `WORKBENCH_WORKSPACE=F:\\Video`; poll `endpoint.json`, require a `127.0.0.1` base URL and HTTP 200 health; terminate only the launched PowerShell process; silently invoke `unins000.exe`; verify marker preservation; write evidence; invoke the report CLI; print the final marker. The runner must never delete `F:\\Video` or the workspace root.

- [x] **Step 4: Verify green and commit**

Run `uv run pytest tests/release/test_launcher_contract.py -v`. Expected: pass. Commit with `git add tests/release/windows-acceptance.ps1 tests/release/test_launcher_contract.py && git commit -m "test: add Windows install acceptance runner"`.

### Task 3: Add optional P01 release gate and handoff documentation

**Files:**

- Modify: `scripts/freeze-release.ps1`
- Modify: `tests/release/test_build_release_script.py`
- Modify: `docs/troubleshooting.md`

**Interfaces:**

- Consumes: optional `-WindowsAcceptanceReport <path>`.
- Produces: `Release blocked: P01 Windows acceptance is not passed.` if a supplied report lacks schema `1.0`, decision `pass`, or an empty `blocking_failures` array.

- [x] **Step 1: Write the failing release-gate test**

```python
def test_release_freeze_requires_a_passing_p01_report_when_one_is_supplied() -> None:
    source = (REPOSITORY_ROOT / "scripts/freeze-release.ps1").read_text(encoding="utf-8")
    assert "WindowsAcceptanceReport" in source
    assert 'decision -ne "pass"' in source
    assert "P01 Windows acceptance is not passed" in source
```

- [x] **Step 2: Verify red**

Run `uv run pytest tests/release/test_build_release_script.py -v`. Expected: fail because the freeze script has no P01 input.

- [x] **Step 3: Implement the optional gate and concise handoff**

Add `[string]$WindowsAcceptanceReport = ""` to `freeze-release.ps1`. If supplied, require its file, parse JSON, and block on schema, decision, or blockers mismatch; old behavior remains unchanged if omitted. Document `powershell -ExecutionPolicy Bypass -File .\\tests\\release\\windows-acceptance.ps1 -InstallerPath .\\release\\ppt-video-workbench-setup.exe`, the report directory, the two markers, and that `F:\\Video` remains intact.

- [x] **Step 4: Run fresh verification and commit**

Run `uv run pytest tests/release/test_windows_acceptance_report.py tests/release/test_launcher_contract.py tests/release/test_build_release_script.py -v`, then `uv run ruff check scripts tests/release`, then `uv run mypy apps/api/src`; all must pass. Commit all P01 documentation with `git commit -m "test: gate release freeze on P01 acceptance"`.

## Plan Self-Review

- Task 1 provides schema, redaction, and fail-closed verdict.
- Task 2 provides install, launch, restart, uninstall, and retention evidence.
- Task 3 makes a supplied report release-blocking and records the Windows handoff.
