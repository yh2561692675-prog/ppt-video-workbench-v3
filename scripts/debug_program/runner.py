"""Fail-closed command runner that records first-failure evidence append-only."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .evidence import EvidenceWriter, sha256_file, utc_now
from .models import validate_automation_verdict

_RUN_ID = re.compile(r"^[a-z0-9][a-z0-9-]{3,127}$")


@dataclass(frozen=True)
class CommandSpec:
    """One executable invocation in a deterministic automation plan."""

    name: str
    argv: tuple[str, ...]
    cwd: Path
    env: dict[str, str]
    timeout_seconds: int = 1800


@dataclass(frozen=True)
class CommandResult:
    name: str
    exit_code: int
    status: str
    stdout: Path
    stderr: Path
    result: Path


def _write_new(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode(
        "utf-8"
    )
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    fd = os.open(path, flags)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def _slug(value: str) -> str:
    slug = "".join(
        char if char.isalnum() or char == "-" else "-" for char in value
    ).strip("-").lower()
    if not slug:
        raise ValueError("command name must contain at least one alphanumeric character")
    return slug


def execute_command(spec: CommandSpec, output_root: Path, index: int) -> CommandResult:
    """Execute one command and never replace any existing output."""

    command_root = output_root / f"{index:03d}-{_slug(spec.name)}"
    command_root.mkdir(parents=True, exist_ok=True)
    stdout = command_root / "stdout.log"
    stderr = command_root / "stderr.log"
    result_path = command_root / "result.json"
    command_metadata = command_root / "command.json"
    _write_new(
        command_metadata,
        {
            "name": spec.name,
            "argv": list(spec.argv),
            "cwd": str(spec.cwd),
            "timeout_seconds": spec.timeout_seconds,
            "started_at": utc_now(),
        },
    )
    status = "passed"
    exit_code = 0
    error: str | None = None
    try:
        with stdout.open("wb") as stdout_handle, stderr.open("wb") as stderr_handle:
            completed = subprocess.run(
                list(spec.argv),
                cwd=spec.cwd,
                env={**os.environ, **spec.env},
                stdout=stdout_handle,
                stderr=stderr_handle,
                timeout=spec.timeout_seconds,
                check=False,
            )
        exit_code = completed.returncode
        if exit_code != 0:
            status = "failed"
    except subprocess.TimeoutExpired as exc:
        status = "failed"
        exit_code = 124
        error = f"timeout after {spec.timeout_seconds}s: {exc}"
    except OSError as exc:
        status = "failed"
        exit_code = 127
        error = f"spawn failed: {exc}"
    finally:
        # The files are opened explicitly to make an interrupted process visible.
        for path in (stdout, stderr):
            if not path.exists():
                path.write_bytes(b"")
    record = {
        "name": spec.name,
        "argv": list(spec.argv),
        "cwd": str(spec.cwd),
        "exit_code": exit_code,
        "status": status,
        "started_at": json.loads(command_metadata.read_text(encoding="utf-8"))["started_at"],
        "finished_at": utc_now(),
        "stdout": {
            "path": stdout.name,
            "size": stdout.stat().st_size,
            "sha256": sha256_file(stdout),
        },
        "stderr": {
            "path": stderr.name,
            "size": stderr.stat().st_size,
            "sha256": sha256_file(stderr),
        },
    }
    if error is not None:
        record["error"] = error
    _write_new(result_path, record)
    return CommandResult(spec.name, exit_code, status, stdout, stderr, result_path)


def run_plan(
    *,
    writer: EvidenceWriter,
    matrix: str,
    commands: Sequence[CommandSpec],
    environment: dict[str, Any] | None = None,
    stop_on_failure: bool = True,
) -> dict[str, Any]:
    """Run commands sequentially, preserving the first failure and all artifacts."""

    if not commands:
        raise ValueError("automation plan must contain at least one command")
    writer.create_run(matrix, environment, status="running")
    command_root = writer.run_root / "commands"
    results: list[CommandResult] = []
    first_failure: dict[str, Any] | None = None
    for index, spec in enumerate(commands, start=1):
        result = execute_command(spec, command_root, index)
        results.append(result)
        if result.status == "failed" and first_failure is None:
            first_failure = {
                "name": result.name,
                "exit_code": result.exit_code,
                "result": result.result.relative_to(writer.run_root).as_posix(),
            }
            if stop_on_failure:
                break
    status = "failed" if first_failure else "passed"
    verdict = {
        "schema_version": "1.0",
        "candidate_id": writer.candidate_id,
        "run_id": writer.run_id,
        "matrix": matrix,
        "status": status,
        "started_at": json.loads(
            (writer.run_root / "run.json").read_text(encoding="utf-8")
        )["started_at"],
        "finished_at": utc_now(),
        "commands": [
            {
                "name": item.name,
                "exit_code": item.exit_code,
                "status": item.status,
                "result": item.result.relative_to(writer.run_root).as_posix(),
            }
            for item in results
        ],
        "first_failure": first_failure,
    }
    validate_automation_verdict(verdict, writer.run_root)
    _write_new(writer.run_root / "automation-verdict.json", verdict)
    writer.manifest()
    return verdict


def recover_automation(writer: EvidenceWriter) -> Path | None:
    """Mark a running automation run interrupted without replacing any file."""

    run_path = writer.run_root / "run.json"
    verdict_path = writer.run_root / "automation-verdict.json"
    if not run_path.is_file() or verdict_path.exists():
        return None
    run = json.loads(run_path.read_text(encoding="utf-8"))
    if run.get("status") != "running":
        return None
    marker = writer.run_root / "automation-interrupted.json"
    if not marker.exists():
        _write_new(
            marker,
            {
                "schema_version": "1.0",
                "candidate_id": writer.candidate_id,
                "run_id": writer.run_id,
                "detected_at": utc_now(),
                "reason": "automation run had no terminal verdict",
            },
        )
    verdict = {
        "schema_version": "1.0",
        "candidate_id": writer.candidate_id,
        "run_id": writer.run_id,
        "matrix": run["matrix"],
        "status": "interrupted",
        "started_at": run["started_at"],
        "finished_at": utc_now(),
        "commands": [],
        "first_failure": None,
        "notes": ["recovered without overwriting the running run"],
    }
    validate_automation_verdict(verdict, writer.run_root)
    _write_new(verdict_path, verdict)
    writer.manifest()
    return verdict_path


def new_run_id(candidate_id: str, matrix: str) -> str:
    """Return a collision-resistant, schema-safe run identifier."""

    import secrets
    import time

    candidate_slug = _slug(candidate_id)[:16].rstrip("-")
    matrix_slug = _slug(matrix)[:24].rstrip("-")
    run_id = f"{candidate_slug}-{matrix_slug}-{time.time_ns()}-{secrets.token_hex(3)}"
    if _RUN_ID.fullmatch(run_id) is None:
        raise ValueError("generated run_id does not satisfy automation verdict contract")
    return run_id


def python_smoke_plan(repo_root: Path) -> tuple[CommandSpec, ...]:
    """Small, deterministic regression used to validate the runner itself."""

    return (
        CommandSpec(
            "debug-program-tests",
            (sys.executable, "-m", "pytest", "-q", "tests/debug_program"),
            repo_root,
            {"PYTHONPATH": os.pathsep.join((".", "apps/api/src", "peripheral-platform/src"))},
            300,
        ),
    )


def full_automation_plan(
    repo_root: Path, candidate: Path | None = None
) -> tuple[CommandSpec, ...]:
    """DP20-DP24 command plan; execution remains sequential and fail-closed."""

    python_env = {
        "PYTHONPATH": os.pathsep.join((".", "apps/api/src", "peripheral-platform/src"))
    }
    python = sys.executable
    pnpm = "pnpm.cmd" if os.name == "nt" else "pnpm"

    def spec(
        name: str,
        argv: Sequence[str],
        timeout_seconds: int,
        env: dict[str, str] | None = None,
    ) -> CommandSpec:
        return CommandSpec(name, tuple(argv), repo_root, env or {}, timeout_seconds)

    tool_preflight_command = [
        python,
        "-m",
        "scripts.debug_program.release_preflight",
        "--repo-root",
        str(repo_root),
        "--phase",
        "tools",
    ]
    release_command = [
        python,
        "-m",
        "scripts.debug_program.release_preflight",
        "--repo-root",
        str(repo_root),
        "--phase",
        "release-inputs",
    ]
    if candidate is not None:
        tool_preflight_command.extend(("--candidate", str(candidate)))
        release_command.extend(("--candidate", str(candidate)))
    release_root = Path("test-results/debug-program/release-payload")
    installer_root = Path("test-results/debug-program/release-artifacts")
    return (
        spec("release-tool-preflight", tool_preflight_command, 300, python_env),
        spec(
            "prepare-runtime",
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(repo_root / "scripts" / "prepare-runtime.ps1"),
                "-Output",
                "runtime-assets",
            ],
            7200,
        ),
        spec("release-input-preflight", release_command, 300, python_env),
        spec(
            "release-build",
            [
                "powershell.exe",
                "-NoProfile",
                "-File",
                str(repo_root / "scripts" / "build-release.ps1"),
                "-Output",
                str(release_root),
                "-InstallerOutputDirectory",
                str(installer_root),
            ],
            7200,
        ),
        spec("python-full-tests", [python, "-m", "pytest", "-q"], 3600, python_env),
        spec(
            "python-ruff",
            [python, "-m", "ruff", "check", "."],
            900,
            python_env,
        ),
        spec("python-mypy", [python, "-m", "mypy", "--strict"], 1800, python_env),
        spec("root-lint", [pnpm, "lint"], 1800),
        spec("root-typecheck", [pnpm, "typecheck"], 1200),
        spec("root-tests", [pnpm, "test"], 2400),
        spec("root-build", [pnpm, "build"], 2400),
        spec(
            "contract-migration-regression",
            [
                python,
                "-m",
                "pytest",
                "-q",
                "tests/contracts",
                "tests/contract",
                "tests/integration/test_project_v2_migration.py",
                "tests/unit/storage/test_workspace_migrations.py",
            ],
            1800,
            python_env,
        ),
        spec(
            "export-contracts-check",
            [python, "scripts/export_contracts.py", "--check"],
            900,
            python_env,
        ),
        spec(
            "cloud-client-check",
            [python, "scripts/generate_cloud_client.py", "--check"],
            900,
            python_env,
        ),
        spec(
            "ci-wiring-check",
            [
                python,
                "-m",
                "scripts.debug_program.ci_preflight",
                "--repo-root",
                str(repo_root),
            ],
            300,
            python_env,
        ),
    )
