from __future__ import annotations

import subprocess
import time
from collections import deque
from collections.abc import Callable, Sequence
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from threading import Thread
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

        stdout_chunks: deque[str] = deque(maxlen=32)
        stderr_chunks: deque[str] = deque(maxlen=32)
        drain_threads: list[Thread] = []
        for stream, chunks in (
            (getattr(process, "stdout", None), stdout_chunks),
            (getattr(process, "stderr", None), stderr_chunks),
        ):
            if stream is not None:
                thread = Thread(target=_drain_output, args=(stream, chunks), daemon=True)
                thread.start()
                drain_threads.append(thread)

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

        if drain_threads:
            process.wait()
            for thread in drain_threads:
                thread.join(timeout=3.0)
            stdout, stderr = "".join(stdout_chunks), "".join(stderr_chunks)
        else:
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
            for stream_name in ("stdout", "stderr"):
                with suppress(Exception):
                    stream = getattr(process, stream_name, None)
                    if stream is not None:
                        stream.close()


def _drain_output(stream: Any, chunks: deque[str]) -> None:
    while True:
        chunk = stream.read(4096)
        if not chunk:
            return
        chunks.append(str(chunk))


def _safe_output(value: object) -> str:
    return redact_text(str(value or ""))[-64 * 1024 :]
