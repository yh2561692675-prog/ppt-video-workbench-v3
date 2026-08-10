from __future__ import annotations

import subprocess
import time
from collections.abc import Callable, Sequence
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from workbench.diagnostics.redaction import redact_text


class ProcessControl(Protocol):
    @property
    def cancel_requested(self) -> bool: ...

    def heartbeat(self) -> None: ...


class NullProcessControl:
    cancel_requested = False

    def heartbeat(self) -> None:
        return None


class ProcessCancelled(RuntimeError):
    pass


@dataclass(frozen=True)
class ProcessResult:
    returncode: int
    stdout: str
    stderr: str


class ProcessExecutionError(RuntimeError):
    def __init__(self, message: str, result: ProcessResult | None = None) -> None:
        super().__init__(message)
        self.result = result


class CancellableProcessRunner:
    def __init__(
        self,
        *,
        popen: Callable[..., Any] = subprocess.Popen,
        sleeper: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.popen = popen
        self.sleeper = sleeper
        self.clock = clock

    def run(
        self,
        command: Sequence[str],
        cwd: Path,
        control: ProcessControl,
    ) -> ProcessResult:
        try:
            process = self.popen(
                list(command),
                cwd=cwd,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                shell=False,
            )
        except OSError as error:
            raise ProcessExecutionError("无法启动渲染进程") from error

        last_heartbeat = self.clock()
        while True:
            if control.cancel_requested:
                self._cancel(process)
                raise ProcessCancelled("render process cancelled")
            returncode = process.poll()
            if returncode is not None:
                break
            now = self.clock()
            if now - last_heartbeat >= 5.0:
                control.heartbeat()
                last_heartbeat = now
            self.sleeper(0.25)

        stdout, stderr = process.communicate()
        result = ProcessResult(
            returncode=int(returncode),
            stdout=_safe_output(stdout),
            stderr=_safe_output(stderr),
        )
        if result.returncode != 0:
            raise ProcessExecutionError(
                f"render process exited with exit code {result.returncode}", result
            )
        return result

    @staticmethod
    def _cancel(process: Any) -> None:
        process.terminate()
        try:
            process.wait(timeout=3.0)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=3.0)
        finally:
            with suppress(Exception):
                process.communicate()


def _safe_output(value: object) -> str:
    return redact_text(str(value or ""))[-64 * 1024 :]
