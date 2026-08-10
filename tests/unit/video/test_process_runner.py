from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from workbench.video.process_runner import (
    CancellableProcessRunner,
    ProcessCancelled,
    ProcessExecutionError,
)


class FakeControl:
    def __init__(self, *, cancelled: bool = False) -> None:
        self.cancel_requested = cancelled
        self.heartbeats = 0

    def heartbeat(self) -> None:
        self.heartbeats += 1


class FakeProcess:
    def __init__(
        self,
        *,
        returncode: int = 0,
        terminate_never_exits: bool = False,
        polls_before_exit: int = 0,
    ) -> None:
        self.returncode = returncode
        self.terminate_never_exits = terminate_never_exits
        self.polls_before_exit = polls_before_exit
        self.poll_count = 0
        self.terminated = False
        self.killed = False
        self.wait_timeouts: list[float] = []

    def poll(self):
        if self.terminate_never_exits and self.terminated and not self.killed:
            return None
        if self.poll_count < self.polls_before_exit:
            self.poll_count += 1
            return None
        return self.returncode

    def communicate(self):
        return ("stdout", "stderr")

    def terminate(self) -> None:
        self.terminated = True

    def kill(self) -> None:
        self.killed = True

    def wait(self, timeout: float | None = None):
        if timeout is not None:
            self.wait_timeouts.append(timeout)
        if self.terminate_never_exits and self.terminated and not self.killed:
            raise subprocess.TimeoutExpired("fake", timeout or 0)
        return self.returncode


def test_runner_returns_process_result_and_redacts_output(tmp_path: Path) -> None:
    process = FakeProcess()
    runner = CancellableProcessRunner(
        popen=lambda *args, **kwargs: process,
        sleeper=lambda _: None,
    )

    result = runner.run(["ffmpeg", "-i", "input"], tmp_path, FakeControl())

    assert result.returncode == 0
    assert result.stdout == "stdout"
    assert result.stderr == "stderr"


def test_runner_raises_for_nonzero_exit(tmp_path: Path) -> None:
    process = FakeProcess(returncode=7)
    runner = CancellableProcessRunner(
        popen=lambda *args, **kwargs: process,
        sleeper=lambda _: None,
    )

    with pytest.raises(ProcessExecutionError, match="exit code 7"):
        runner.run(["ffmpeg"], tmp_path, FakeControl())


def test_cancel_terminates_then_kills_after_three_seconds(tmp_path: Path) -> None:
    process = FakeProcess(terminate_never_exits=True)
    runner = CancellableProcessRunner(
        popen=lambda *args, **kwargs: process,
        sleeper=lambda _: None,
    )

    with pytest.raises(ProcessCancelled):
        runner.run(["ffmpeg"], tmp_path, FakeControl(cancelled=True))

    assert process.terminated is True
    assert process.killed is True
    assert 3.0 in process.wait_timeouts


def test_runner_heartbeats_after_five_seconds(tmp_path: Path) -> None:
    process = FakeProcess(polls_before_exit=21)
    elapsed = 0.0
    control = FakeControl()

    def sleeper(seconds: float) -> None:
        nonlocal elapsed
        elapsed += seconds

    runner = CancellableProcessRunner(
        popen=lambda *args, **kwargs: process,
        sleeper=sleeper,
        clock=lambda: elapsed,
    )
    runner.run(["ffmpeg"], tmp_path, control)

    assert control.heartbeats >= 1
