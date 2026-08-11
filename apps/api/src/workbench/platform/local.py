"""Portable local implementations with platform differences kept at the edge."""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import signal
import subprocess
import tempfile
import time
import webbrowser
from collections.abc import Sequence
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from pathlib import Path, PurePosixPath
from typing import Literal
from urllib.parse import urlparse

from workbench.contracts.p2_platform import canonical_sha256, normalize_logical_path

from .credentials import PlatformCredentialStore, system_credential_backend
from .models import (
    CapabilityStateV1,
    PlatformCapabilitySnapshotV1,
    PlatformInfoV1,
    PlatformPathError,
    ProcessResultV1,
    ProcessServiceError,
    ToolInfoV1,
)


class LocalPathService:
    _DIRECTORIES = {
        "app_data": "app-data",
        "workspace_data": "workspace-data",
        "cache": "cache",
        "logs": "logs",
        "runtime": "runtime",
        "temp": "temp",
        "downloads": "downloads",
    }

    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir.resolve()

    def directory(self, logical_directory: str) -> Path:
        try:
            name = self._DIRECTORIES[logical_directory]
        except KeyError as error:
            raise PlatformPathError("unknown logical directory") from error
        path = (self.base_dir / name).resolve()
        self._ensure_inside(path, self.base_dir)
        path.mkdir(parents=True, exist_ok=True)
        return path

    def logical_to_local(self, logical_path: str, *, root: str = "workspace_data") -> Path:
        try:
            normalized = normalize_logical_path(logical_path)
        except ValueError as error:
            raise PlatformPathError(str(error)) from error
        candidate = (self.directory(root) / PurePosixPath(normalized)).resolve()
        self._ensure_inside(candidate, self.directory(root))
        return candidate

    @staticmethod
    def _ensure_inside(path: Path, root: Path) -> None:
        try:
            path.relative_to(root)
        except ValueError as error:
            raise PlatformPathError("path escaped logical root") from error


class LocalAtomicFileService:
    def __init__(self, paths: LocalPathService) -> None:
        self.paths = paths

    def write_bytes(self, target: Path, content: bytes) -> None:
        destination = target.resolve()
        self._ensure_allowed(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        handle, temporary_name = tempfile.mkstemp(
            prefix=f".{destination.name}.", dir=destination.parent
        )
        try:
            with os.fdopen(handle, "wb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary_name, destination)
        except BaseException:
            with suppress(FileNotFoundError):
                os.unlink(temporary_name)
            raise

    def read_bytes(self, target: Path) -> bytes:
        destination = target.resolve()
        self._ensure_allowed(destination)
        return destination.read_bytes()

    def _ensure_allowed(self, target: Path) -> None:
        for root_name in LocalPathService._DIRECTORIES:
            root = self.paths.directory(root_name)
            try:
                target.relative_to(root)
                return
            except ValueError:
                continue
        raise PlatformPathError("file is outside platform data roots")


class LocalProcessService:
    def run(
        self,
        argv: Sequence[str],
        *,
        cwd: Path | None = None,
        timeout_ms: int = 120_000,
        max_output_bytes: int = 1_000_000,
    ) -> ProcessResultV1:
        if not argv or any(not isinstance(item, str) or not item for item in argv):
            raise ProcessServiceError("invalid_argv", "argv must be a non-empty string array")
        if timeout_ms < 1 or max_output_bytes < 1:
            raise ProcessServiceError(
                "invalid_limits", "timeout and output limits must be positive"
            )
        started = time.monotonic()
        timed_out = False
        cancelled = False
        with tempfile.TemporaryFile() as stdout_file, tempfile.TemporaryFile() as stderr_file:
            try:
                if os.name == "nt":
                    process = subprocess.Popen(
                        list(argv),
                        cwd=cwd,
                        stdout=stdout_file,
                        stderr=stderr_file,
                        stdin=subprocess.DEVNULL,
                        shell=False,
                        text=False,
                        creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
                    )
                else:
                    process = subprocess.Popen(
                        list(argv),
                        cwd=cwd,
                        stdout=stdout_file,
                        stderr=stderr_file,
                        stdin=subprocess.DEVNULL,
                        shell=False,
                        text=False,
                        start_new_session=True,
                    )
            except OSError as error:
                raise ProcessServiceError(
                    "process_start_failed", "Unable to start requested process"
                ) from error
            try:
                process.communicate(timeout=timeout_ms / 1000)
            except subprocess.TimeoutExpired:
                timed_out = True
                self._terminate(process)
                process.communicate()
            except KeyboardInterrupt:
                cancelled = True
                self._terminate(process)
                process.communicate()
            stdout_file.seek(0)
            stderr_file.seek(0)
            stdout = stdout_file.read(max_output_bytes + 1)
            stderr = stderr_file.read(max_output_bytes + 1)
        output_truncated = len(stdout) > max_output_bytes or len(stderr) > max_output_bytes
        duration = int((time.monotonic() - started) * 1000)
        return ProcessResultV1(
            argv=list(argv),
            return_code=process.returncode if process.returncode is not None else -1,
            stdout=stdout[:max_output_bytes].decode("utf-8", errors="replace"),
            stderr=stderr[:max_output_bytes].decode("utf-8", errors="replace"),
            timed_out=timed_out,
            cancelled=cancelled,
            output_truncated=output_truncated,
            duration_ms=duration,
        )

    @staticmethod
    def _terminate(process: subprocess.Popen[bytes]) -> None:
        if process.poll() is not None:
            return
        if os.name == "nt":
            process.kill()
            return
        killpg = getattr(os, "killpg", None)
        if callable(killpg):
            with suppress(ProcessLookupError):
                killpg(process.pid, signal.SIGTERM)
        else:
            process.terminate()
        try:
            process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            if callable(killpg):
                with suppress(ProcessLookupError):
                    killpg(process.pid, getattr(signal, "SIGKILL", signal.SIGTERM))
            else:
                process.kill()


class LocalToolDiscoveryService:
    _NAME_RE = re.compile(r"^[a-z][a-z0-9_.-]{0,63}$")
    _PROBES: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
        "ffmpeg": (("-version",), ("media.decode", "media.encode")),
        "ffprobe": (("-version",), ("media.inspect",)),
        "soffice": (("--version",), ("office.render",)),
        "libreoffice": (("--version",), ("office.render",)),
    }

    def __init__(self, *, bundled_root: Path | None = None) -> None:
        self.bundled_root = bundled_root.resolve() if bundled_root else None
        self._cache: dict[str, ToolInfoV1] = {}

    def find(self, name: str) -> ToolInfoV1:
        if not self._NAME_RE.fullmatch(name):
            raise ValueError("tool name must be a simple executable name")
        if name in self._cache:
            return self._cache[name]
        bundled = (self.bundled_root / name) if self.bundled_root else None
        if bundled is not None:
            bundled = bundled.resolve()
            assert self.bundled_root is not None
            try:
                bundled.relative_to(self.bundled_root)
            except ValueError:
                bundled = None
        executable = bundled if bundled and bundled.is_file() else Path(shutil.which(name) or "")
        if not executable or not executable.is_file():
            result = ToolInfoV1(name=name, available=False, source="unavailable")
        else:
            source: Literal["bundled", "supported_system"] = (
                "bundled" if bundled and executable == bundled else "supported_system"
            )
            logical_source = "runtime" if source == "bundled" else "system"
            version, capabilities = self._probe(executable, name)
            result = ToolInfoV1(
                name=name,
                available=True,
                executable_ref=f"{logical_source}://{name}",
                source=source,
                version=version,
                sha256=self._hash_file(executable),
                capabilities=list(capabilities),
            )
        self._cache[name] = result
        return result

    def _probe(self, executable: Path, name: str) -> tuple[str | None, tuple[str, ...]]:
        args, capabilities = self._PROBES.get(name, (("--version",), ()))
        try:
            completed = subprocess.run(
                [str(executable), *args],
                check=False,
                capture_output=True,
                timeout=2,
                shell=False,
            )
        except (OSError, subprocess.SubprocessError):
            return None, capabilities
        output = (completed.stdout + completed.stderr)[:4096].decode("utf-8", errors="replace")
        first_line = next((line.strip() for line in output.splitlines() if line.strip()), "")
        return first_line[:100] or None, capabilities

    @staticmethod
    def _hash_file(path: Path) -> str | None:
        try:
            digest_builder = hashlib.sha256()
            with path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest_builder.update(chunk)
            digest = digest_builder.hexdigest()
        except OSError:
            return None
        return f"sha256:{digest}"


class LocalBrowserService:
    def open(self, url: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            raise ValueError("only HTTP(S) browser targets are allowed")
        webbrowser.open(url)


class LocalMediaRuntimeService:
    def __init__(self, tools: LocalToolDiscoveryService) -> None:
        self.tools = tools

    def ffmpeg(self) -> ToolInfoV1:
        return self.tools.find("ffmpeg")

    def ffprobe(self) -> ToolInfoV1:
        return self.tools.find("ffprobe")

    def snapshot(self) -> dict[str, object]:
        """Return deterministic media capability metadata without running user input."""

        ffmpeg = self.ffmpeg()
        ffprobe = self.ffprobe()
        return {
            "ffmpeg": ffmpeg.model_dump(mode="json"),
            "ffprobe": ffprobe.model_dump(mode="json"),
            "software_fallback": not (ffmpeg.available and ffprobe.available),
            "capabilities": [
                capability
                for tool in (ffmpeg, ffprobe)
                for capability in tool.capabilities
            ],
        }


class LocalOfficeRenderService:
    def __init__(self, tools: LocalToolDiscoveryService) -> None:
        self.tools = tools

    def renderer(self) -> ToolInfoV1:
        soffice = self.tools.find("soffice")
        if soffice.available:
            return soffice
        return self.tools.find("libreoffice")

    def snapshot(self) -> dict[str, object]:
        renderer = self.renderer()
        native_office = self.tools.find("soffice").available
        return {
            "renderer": renderer.model_dump(mode="json"),
            "powerpoint_compatibility": "native" if native_office else "degraded",
            "network_access": False,
            "macro_execution": False,
        }


class LocalUpdateService:
    def __init__(self, app_version: str) -> None:
        self._app_version = app_version

    def current_version(self) -> str:
        return self._app_version


class LocalPowerService:
    def prevent_sleep(self, reason: str) -> str:
        if not reason.strip():
            raise ValueError("reason is required")
        return f"noop:{reason.strip()}"


class LocalPlatformServices:
    def __init__(
        self,
        base_dir: Path,
        *,
        app_version: str,
        platform: Literal["windows", "macos", "linux"],
        architecture: str,
    ) -> None:
        self.info = PlatformInfoV1(
            platform=platform,
            architecture=architecture,
            runtime_version="python-3.12",
            app_version=app_version,
        )
        self.paths = LocalPathService(base_dir)
        self.files = LocalAtomicFileService(self.paths)
        self.processes = LocalProcessService()
        self.credentials = PlatformCredentialStore(system_credential_backend(platform))
        self.tools = LocalToolDiscoveryService(bundled_root=self.paths.directory("runtime"))
        self.browser = LocalBrowserService()
        self.media = LocalMediaRuntimeService(self.tools)
        self.office = LocalOfficeRenderService(self.tools)
        self.updates = LocalUpdateService(app_version)
        self.power = LocalPowerService()

    def capabilities(self) -> PlatformCapabilitySnapshotV1:
        tools = [self.media.ffmpeg(), self.media.ffprobe(), self.office.renderer()]
        capabilities = ["paths", "atomic_files", "processes", "credentials", "browser"]
        if all(tool.available for tool in tools[:2]):
            capabilities.append("media.ffmpeg")
        if tools[2].available:
            capabilities.append("office.libreoffice")
        capability_states = [
            CapabilityStateV1(capability_id=item, status="supported") for item in capabilities
        ]
        if not self.credentials.backend.available:
            capability_states = [
                state
                for state in capability_states
                if state.capability_id != "credentials"
            ] + [
                CapabilityStateV1(
                    capability_id="credentials",
                    status="misconfigured",
                    detail=f"{self.credentials.backend.name} binding is not installed",
                )
            ]
        if not tools[0].available or not tools[1].available:
            capability_states.append(
                CapabilityStateV1(
                    capability_id="media.ffmpeg",
                    status="missing",
                    detail="ffmpeg and ffprobe are required",
                )
            )
        if not tools[2].available:
            capability_states.append(
                CapabilityStateV1(
                    capability_id="office.libreoffice",
                    status="missing",
                    detail="LibreOffice is not installed",
                )
            )
        native_office = self.tools.find("powerpnt")
        if self.info.platform == "windows":
            capability_states.append(
                CapabilityStateV1(
                    capability_id="office.powerpoint_native",
                    status="supported" if native_office.available else "missing",
                    detail=(
                        None
                        if native_office.available
                        else "PowerPoint runtime is not installed"
                    ),
                )
            )
        else:
            capability_states.append(
                CapabilityStateV1(
                    capability_id="office.powerpoint_native",
                    status="unsupported",
                    detail="PowerPoint COM is available only on Windows",
                )
            )
        fingerprint = canonical_sha256(
            {
                "info": self.info.model_dump(mode="json"),
                "tools": [tool.model_dump(mode="json") for tool in tools],
            }
        )
        return PlatformCapabilitySnapshotV1(
            info=self.info,
            capabilities=capabilities,
            capability_states=capability_states,
            tools=tools,
            fingerprint=fingerprint,
            generated_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            expires_at=(datetime.now(UTC) + timedelta(minutes=15))
            .isoformat()
            .replace("+00:00", "Z"),
        )
