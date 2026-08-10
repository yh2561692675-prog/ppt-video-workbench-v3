from __future__ import annotations

import os
import re
import subprocess
import sys
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID, uuid4

from peripheral_contracts import EventEnvelope, JobEnvelope, JobResult, ModuleManifest
from pydantic import JsonValue, ValidationError

_INHERITED_ENVIRONMENT = (
    "PATH",
    "SYSTEMROOT",
    "WINDIR",
    "TEMP",
    "TMP",
    "LOCALAPPDATA",
)
_BEARER_PATTERN = re.compile(r"(?i)Bearer\s+[A-Za-z0-9._~+/=-]+")


class ModuleNotRegistered(LookupError):
    def __init__(self, job_type: str) -> None:
        super().__init__(f"no peripheral module registered for {job_type!r}")
        self.job_type = job_type


@dataclass(frozen=True, slots=True)
class RegisteredModule:
    manifest: ModuleManifest
    command: tuple[str, ...]
    environment: tuple[tuple[str, str], ...] = ()
    parameter_validator: Callable[[dict[str, JsonValue]], object] | None = None

    def validate_parameters(self, parameters: dict[str, JsonValue]) -> None:
        if self.parameter_validator is not None:
            self.parameter_validator(parameters)


class ModuleRegistry:
    def __init__(self, modules: Iterable[RegisteredModule]) -> None:
        self._by_job_type: dict[str, RegisteredModule] = {}
        for module in modules:
            for job_type in module.manifest.job_types:
                if job_type in self._by_job_type:
                    raise ValueError(f"duplicate job type registration: {job_type}")
                self._by_job_type[job_type] = module

    def resolve(self, job_type: str) -> RegisteredModule:
        try:
            return self._by_job_type[job_type]
        except KeyError as error:
            raise ModuleNotRegistered(job_type) from error


@dataclass(frozen=True, slots=True)
class JobAttemptRecord:
    attempt_id: UUID
    job_id: UUID
    attempt_number: int
    root: Path

    @property
    def request_path(self) -> Path:
        return self.root / "request.json"

    @property
    def result_path(self) -> Path:
        return self.root / "result.json"

    @property
    def stdout_path(self) -> Path:
        return self.root / "stdout.ndjson"

    @property
    def stderr_path(self) -> Path:
        return self.root / "stderr.log"


@dataclass(slots=True)
class RunningModule:
    job: JobEnvelope
    attempt: JobAttemptRecord
    registered_module: RegisteredModule
    process: subprocess.Popen[str]


@dataclass(frozen=True, slots=True)
class ModuleExecutionResult:
    attempt: JobAttemptRecord
    exit_code: int
    result: JobResult | None
    events: tuple[EventEnvelope, ...]
    validation_error: str | None
    stderr: str
    timed_out: bool


class ModuleRunner:
    def __init__(self, registry: ModuleRegistry, attempts_root: Path) -> None:
        self.registry = registry
        self.attempts_root = attempts_root.resolve()

    def run(
        self,
        job: JobEnvelope,
        attempt: JobAttemptRecord | None = None,
    ) -> ModuleExecutionResult:
        registered = self.registry.resolve(job.job_type)
        selected_attempt = attempt or JobAttemptRecord(
            attempt_id=uuid4(),
            job_id=job.job_id,
            attempt_number=1,
            root=self.attempts_root / str(job.job_id) / uuid4().hex,
        )
        running = self.start(job, selected_attempt)
        return self.wait(running, registered.manifest.max_runtime_seconds)

    def start(self, job: JobEnvelope, attempt: JobAttemptRecord) -> RunningModule:
        registered = self.registry.resolve(job.job_type)
        if attempt.job_id != job.job_id:
            raise ValueError("attempt job_id does not match request job_id")
        attempt.root.mkdir(parents=True, exist_ok=False)
        _write_text_atomic(attempt.request_path, job.model_dump_json(indent=2) + "\n")

        command = [
            *registered.command,
            "--request",
            str(attempt.request_path),
            "--result",
            str(attempt.result_path),
        ]
        process = subprocess.Popen(
            command,
            cwd=attempt.root,
            env=_module_environment(registered),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        return RunningModule(
            job=job,
            attempt=attempt,
            registered_module=registered,
            process=process,
        )

    def wait(
        self,
        running: RunningModule,
        timeout_seconds: float,
    ) -> ModuleExecutionResult:
        timed_out = False
        try:
            stdout, stderr = running.process.communicate(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            timed_out = True
            self.cancel(running, grace_seconds=2.0)
            stdout, stderr = running.process.communicate()

        return self._execution_result(running, stdout, stderr, timed_out=timed_out)

    def collect(
        self,
        running: RunningModule,
        *,
        timed_out: bool = False,
    ) -> ModuleExecutionResult:
        stdout, stderr = running.process.communicate()
        return self._execution_result(running, stdout, stderr, timed_out=timed_out)

    @staticmethod
    def _execution_result(
        running: RunningModule,
        stdout: str,
        stderr: str,
        *,
        timed_out: bool,
    ) -> ModuleExecutionResult:

        redacted_stderr = _redact_stderr(stderr)
        running.attempt.stdout_path.write_text(stdout, encoding="utf-8")
        running.attempt.stderr_path.write_text(redacted_stderr, encoding="utf-8")
        events, event_error = _parse_events(stdout)
        result, result_error = _read_result(running.attempt.result_path, running.job.job_id)
        validation_error = event_error or result_error
        if timed_out:
            validation_error = "module execution timed out"
        exit_code = running.process.returncode
        if exit_code is None:
            raise RuntimeError("module process has no exit code after communicate")
        return ModuleExecutionResult(
            attempt=running.attempt,
            exit_code=exit_code,
            result=result,
            events=events,
            validation_error=validation_error,
            stderr=redacted_stderr,
            timed_out=timed_out,
        )

    @staticmethod
    def cancel(running: RunningModule, grace_seconds: float) -> None:
        if running.process.poll() is not None:
            return
        running.process.terminate()
        try:
            running.process.wait(timeout=grace_seconds)
        except subprocess.TimeoutExpired:
            running.process.kill()
            running.process.wait()


def echo_registered_module() -> RegisteredModule:
    from peripheral_modules.echo import validate_parameters

    source_root = Path(__file__).resolve().parents[1]
    frozen = bool(getattr(sys, "frozen", False))
    return RegisteredModule(
        manifest=ModuleManifest(
            schema_version="1.0",
            module_name="echo",
            module_version="1.0.0",
            job_types=("system.echo",),
            max_runtime_seconds=45,
        ),
        command=(
            (sys.executable, "--run-module", "echo")
            if frozen
            else (sys.executable, "-m", "peripheral_modules.echo")
        ),
        environment=() if frozen else (("PYTHONPATH", str(source_root)),),
        parameter_validator=validate_parameters,
    )


def _module_environment(module: RegisteredModule) -> dict[str, str]:
    environment = {
        name: value
        for name in _INHERITED_ENVIRONMENT
        if (value := os.environ.get(name)) is not None
    }
    environment.update(module.environment)
    environment["PYTHONIOENCODING"] = "utf-8"
    environment["PYTHONUTF8"] = "1"
    return environment


def _parse_events(stdout: str) -> tuple[tuple[EventEnvelope, ...], str | None]:
    events: list[EventEnvelope] = []
    for line_number, line in enumerate(stdout.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            events.append(EventEnvelope.model_validate_json(line))
        except ValidationError:
            return tuple(events), f"invalid event envelope on stdout line {line_number}"
    return tuple(events), None


def _read_result(path: Path, job_id: UUID) -> tuple[JobResult | None, str | None]:
    if not path.is_file():
        return None, "module result file is missing"
    try:
        result = JobResult.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValidationError) as error:
        return None, f"module result failed validation: {type(error).__name__}"
    if result.job_id != job_id:
        return None, "module result job_id does not match request"
    return result, None


def _redact_stderr(stderr: str) -> str:
    return _BEARER_PATTERN.sub("Bearer ***", stderr)


def _write_text_atomic(path: Path, content: str) -> None:
    temporary = path.with_name(f"{path.name}.tmp")
    with temporary.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)
