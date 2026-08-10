from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from peripheral_contracts import JobEnvelope, JobResult
from peripheral_host.module_runner import ModuleRegistry, ModuleRunner, echo_registered_module


@pytest.fixture
def runner(tmp_path: Path) -> ModuleRunner:
    return ModuleRunner(ModuleRegistry([echo_registered_module()]), tmp_path / "attempts")


def _with_mode(job: JobEnvelope, mode: str, text: str = "echo contract") -> JobEnvelope:
    return job.model_copy(update={"parameters": {"text": text, "fail_mode": mode}})


def test_echo_module_writes_valid_result(runner: ModuleRunner, job: JobEnvelope):
    execution = runner.run(_with_mode(job, "none"))

    assert execution.exit_code == 0
    assert execution.validation_error is None
    assert execution.result is not None
    assert execution.result.outcome == "succeeded"
    assert execution.result.outputs[0].logical_name == "echo-text"
    assert (execution.attempt.root / "echo.txt").read_text(encoding="utf-8") == "echo contract"
    assert [event.event_type for event in execution.events] == [
        "module.started",
        "module.completed",
    ]


def test_retryable_mode_returns_retryable_provider_error(
    runner: ModuleRunner,
    job: JobEnvelope,
):
    execution = runner.run(_with_mode(job, "retryable"))

    assert execution.result is not None
    assert execution.result.outcome == "failed"
    assert execution.result.error is not None
    assert execution.result.error.retryable is True
    assert execution.result.error.category == "PROVIDER"


def test_permanent_mode_returns_non_retryable_input_error(
    runner: ModuleRunner,
    job: JobEnvelope,
):
    execution = runner.run(_with_mode(job, "permanent"))

    assert execution.result is not None
    assert execution.result.outcome == "failed"
    assert execution.result.error is not None
    assert execution.result.error.retryable is False
    assert execution.result.error.category == "INPUT"


def test_invalid_result_is_not_success(runner: ModuleRunner, job: JobEnvelope):
    execution = runner.run(_with_mode(job, "invalid_result"))

    assert execution.exit_code == 0
    assert execution.result is None
    assert execution.validation_error is not None


def test_command_injection_text_is_written_as_data(
    runner: ModuleRunner,
    job: JobEnvelope,
    tmp_path: Path,
):
    payload = '"; touch command-was-executed; #'

    execution = runner.run(_with_mode(job, "none", text=payload))

    assert execution.result is not None
    assert (execution.attempt.root / "echo.txt").read_text(encoding="utf-8") == payload
    assert not (tmp_path / "command-was-executed").exists()


def test_bundled_host_dispatches_echo_module(
    tmp_path: Path,
    job: JobEnvelope,
) -> None:
    request = tmp_path / "request.json"
    result = tmp_path / "result.json"
    request.write_text(_with_mode(job, "none").model_dump_json(), encoding="utf-8")
    source_root = Path(__file__).resolve().parents[2] / "src"
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(source_root)

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "peripheral_host",
            "--run-module",
            "echo",
            "--request",
            str(request),
            "--result",
            str(result),
        ],
        cwd=tmp_path,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert completed.returncode == 0, completed.stderr
    assert JobResult.model_validate_json(result.read_text(encoding="utf-8")).outcome == "succeeded"
    assert (tmp_path / "echo.txt").read_text(encoding="utf-8") == "echo contract"
