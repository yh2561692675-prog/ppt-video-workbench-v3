from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from uuid import uuid4

import pytest
from peripheral_contracts import ArtifactRef, JobEnvelope
from peripheral_host.module_runner import (
    JobAttemptRecord,
    ModuleNotRegistered,
    ModuleRegistry,
    ModuleRunner,
    _restore_recovery_state,
    echo_registered_module,
)


def test_runner_rejects_unregistered_job_type(tmp_path: Path, job: JobEnvelope):
    runner = ModuleRunner(ModuleRegistry([echo_registered_module()]), tmp_path)
    unknown = job.model_copy(update={"job_type": "qa.video"})

    with pytest.raises(ModuleNotRegistered):
        runner.run(unknown)


def test_registry_rejects_duplicate_job_type():
    module = echo_registered_module()

    with pytest.raises(ValueError, match="duplicate job type"):
        ModuleRegistry([module, module])


def test_frozen_echo_module_uses_owned_executable_dispatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "frozen", True, raising=False)

    registered = echo_registered_module()

    assert registered.command == (sys.executable, "--run-module", "echo")
    assert registered.environment == ()


def test_runner_stages_verified_inputs_inside_attempt(tmp_path: Path, job: JobEnvelope) -> None:
    source = tmp_path / "source.bin"
    source.write_bytes(b"verified input")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    input_job = job.model_copy(
        update={
            "inputs": (
                ArtifactRef(
                    artifact_id=uuid4(),
                    kind="binary",
                    path="source.bin",
                    size_bytes=source.stat().st_size,
                    sha256=digest,
                ),
            )
        }
    )
    runner = ModuleRunner(
        ModuleRegistry([echo_registered_module()]),
        tmp_path / "attempts",
        workspace_root=tmp_path,
    )

    execution = runner.run(input_job)
    staged_job = JobEnvelope.model_validate_json(execution.attempt.request_path.read_text())
    staged_path = execution.attempt.root / staged_job.inputs[0].path

    assert execution.exit_code == 0
    assert staged_path.read_bytes() == b"verified input"
    assert staged_path.is_relative_to(execution.attempt.root)


def test_runner_restores_only_previous_attempt_recovery_state(tmp_path: Path) -> None:
    job_id = uuid4()
    previous = tmp_path / "0001" / "recovery"
    previous.mkdir(parents=True)
    (previous / "paid-requests.json").write_text('{"schema_version":1}', encoding="utf-8")
    (previous / "untrusted.bin").write_bytes(b"must not copy")
    (tmp_path / "0001" / "stderr.log").write_text("must not copy", encoding="utf-8")
    current_root = tmp_path / "0002"
    current_root.mkdir()
    attempt = JobAttemptRecord(uuid4(), job_id, 2, current_root)

    _restore_recovery_state(attempt)

    assert (current_root / "recovery" / "paid-requests.json").is_file()
    assert not (current_root / "recovery" / "untrusted.bin").exists()
    assert not (current_root / "stderr.log").exists()
