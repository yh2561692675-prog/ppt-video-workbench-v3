from __future__ import annotations

import sys
from pathlib import Path

import pytest
from peripheral_contracts import JobEnvelope
from peripheral_host.module_runner import (
    ModuleNotRegistered,
    ModuleRegistry,
    ModuleRunner,
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
