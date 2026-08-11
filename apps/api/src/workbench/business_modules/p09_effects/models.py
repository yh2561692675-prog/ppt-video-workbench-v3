from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from workbench.domain.effects import EffectPlanRecord
from workbench.effects.planner import EffectPlanningInput
from workbench.video.models import ProjectVideoProps, SubtitlePlacement


class StrictPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EffectPlanParameters(EffectPlanningInput):
    reduced_motion: bool = False


class VideoPropsBuildParameters(StrictPayload):
    props: ProjectVideoProps
    layout_report: tuple[SubtitlePlacement, ...] = ()


class ArtifactDescriptor(StrictPayload):
    logical_name: str = Field(min_length=1)
    relative_path: str = Field(min_length=1)
    size_bytes: int = Field(ge=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class EffectPlanPayload(StrictPayload):
    record: EffectPlanRecord
    generated_at: datetime
    artifact: ArtifactDescriptor


class ProjectVideoPropsPayload(StrictPayload):
    props: ProjectVideoProps
    layout_report: tuple[SubtitlePlacement, ...] = ()
    generated_at: datetime
    artifact: ArtifactDescriptor
