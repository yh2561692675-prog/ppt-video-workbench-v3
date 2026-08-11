from __future__ import annotations

from datetime import datetime
from typing import Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from workbench.domain.issues import PreflightReport
from workbench.video.models import ProjectVideoProps


class StrictPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RenderGate(StrictPayload):
    preflight_report: PreflightReport

    @model_validator(mode="after")
    def validate_gate(self) -> Self:
        if not self.preflight_report.allowed:
            raise ValueError("PREFLIGHT_BLOCKED: P10 report does not allow rendering")
        return self


class VideoRenderParameters(RenderGate):
    props: ProjectVideoProps
    input_relative_paths: tuple[str, ...]
    runtime_version: str = Field(min_length=1)


class VideoAssembleParameters(RenderGate):
    props: ProjectVideoProps
    segment_count: int = Field(ge=1)


class PackageBuildParameters(RenderGate):
    package_relative_paths: tuple[str, ...] = Field(min_length=1)
    duration_ms: int = Field(gt=0)
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    video_codec: str = Field(min_length=1)
    audio_codec: str = Field(min_length=1)


class ArtifactDescriptor(StrictPayload):
    logical_name: str = Field(min_length=1)
    relative_path: str = Field(min_length=1)
    size_bytes: int = Field(ge=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class PageSegment(ArtifactDescriptor):
    page_id: UUID
    page_order: int = Field(ge=1)
    cache_key: str = Field(pattern=r"^[0-9a-f]{64}$")
    cached: bool = False


class PageSegmentsPayload(StrictPayload):
    generated_at: datetime
    preflight_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    segments: tuple[PageSegment, ...] = Field(min_length=1)


class VideoAssemblePayload(StrictPayload):
    generated_at: datetime
    preflight_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    video: ArtifactDescriptor
    duration_ms: int = Field(gt=0)
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    video_codec: str = Field(min_length=1)
    audio_codec: str = Field(min_length=1)


class PackageFile(StrictPayload):
    relative_path: str = Field(min_length=1)
    size_bytes: int = Field(ge=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class PackageManifestPayload(StrictPayload):
    generated_at: datetime
    preflight_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    files: tuple[PackageFile, ...] = Field(min_length=1)
    file_count: int = Field(ge=1)
    package: ArtifactDescriptor
    duration_ms: int = Field(gt=0)
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    video_codec: str = Field(min_length=1)
    audio_codec: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_count(self) -> Self:
        if self.file_count != len(self.files):
            raise ValueError("package file_count does not match files")
        return self
