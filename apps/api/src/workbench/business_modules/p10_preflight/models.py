from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from workbench.domain.issues import PreflightReport, PreflightScope
from workbench.domain.models import ProjectManifest
from workbench.video.models import VideoPreflight


class StrictPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PreviewBuildParameters(StrictPayload):
    preview: VideoPreflight
    reduced_motion: bool = False


class PreflightRunParameters(StrictPayload):
    project_manifest: ProjectManifest
    scope: tuple[PreflightScope, ...] = (
        "materials",
        "content",
        "audio",
        "video",
        "presenter",
        "runtime",
        "resources",
    )
    previous_report: PreflightReport | None = None


class ArtifactDescriptor(StrictPayload):
    logical_name: str = Field(min_length=1)
    relative_path: str = Field(min_length=1)
    size_bytes: int = Field(ge=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class VideoPreviewPayload(StrictPayload):
    preview: VideoPreflight
    reduced_motion: bool
    generated_at: datetime
    artifact: ArtifactDescriptor


class PreflightReportPayload(StrictPayload):
    report: PreflightReport
    generated_at: datetime
    artifacts: tuple[ArtifactDescriptor, ArtifactDescriptor]
