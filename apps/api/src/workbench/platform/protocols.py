"""Platform service protocols consumed by domain modules."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

from workbench.providers.credentials import CredentialStore

from .models import (
    PlatformCapabilitySnapshotV1,
    PlatformInfoV1,
    ProcessResultV1,
    ToolInfoV1,
)


class PlatformPathService(Protocol):
    def directory(self, logical_directory: str) -> Path: ...

    def logical_to_local(self, logical_path: str, *, root: str = "workspace_data") -> Path: ...


class AtomicFileService(Protocol):
    def write_bytes(self, target: Path, content: bytes) -> None: ...

    def read_bytes(self, target: Path) -> bytes: ...


class ProcessService(Protocol):
    def run(
        self,
        argv: Sequence[str],
        *,
        cwd: Path | None = None,
        timeout_ms: int = 120_000,
        max_output_bytes: int = 1_000_000,
    ) -> ProcessResultV1: ...


class ToolDiscoveryService(Protocol):
    def find(self, name: str) -> ToolInfoV1: ...


class BrowserService(Protocol):
    def open(self, url: str) -> None: ...


class MediaRuntimeService(Protocol):
    def ffmpeg(self) -> ToolInfoV1: ...

    def ffprobe(self) -> ToolInfoV1: ...


class OfficeRenderService(Protocol):
    def renderer(self) -> ToolInfoV1: ...


class UpdatePlatformService(Protocol):
    def current_version(self) -> str: ...


class PowerStateService(Protocol):
    def prevent_sleep(self, reason: str) -> str: ...


class PlatformServices(Protocol):
    info: PlatformInfoV1
    paths: PlatformPathService
    files: AtomicFileService
    processes: ProcessService
    credentials: CredentialStore
    tools: ToolDiscoveryService
    browser: BrowserService
    media: MediaRuntimeService
    office: OfficeRenderService
    updates: UpdatePlatformService
    power: PowerStateService

    def capabilities(self) -> PlatformCapabilitySnapshotV1: ...
