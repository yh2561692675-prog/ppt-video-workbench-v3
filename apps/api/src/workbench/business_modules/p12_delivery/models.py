from __future__ import annotations

from datetime import datetime
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from workbench.business_modules.p11_render.models import PackageManifestPayload


class StrictPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MediaProbe(StrictPayload):
    video_codec: str = Field(min_length=1)
    audio_codec: str = Field(min_length=1)
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    fps: float = Field(gt=0)
    duration_ms: int = Field(gt=0)
    audio_duration_ms: int = Field(gt=0)


class DeliveryPolicy(StrictPayload):
    video_codec: str = "h264"
    audio_codec: str = "aac"
    width: int = 1920
    height: int = 1080
    fps: float = 30
    duration_tolerance_ms: int = Field(default=150, ge=0)
    required_evidence: tuple[str, ...] = ()
    required_signers: tuple[str, ...] = ()


class QualityVerifyParameters(StrictPayload):
    package_manifest: PackageManifestPayload
    policy: DeliveryPolicy = Field(default_factory=DeliveryPolicy)
    evidence: tuple[str, ...] = ()


class QualityCheck(StrictPayload):
    code: str = Field(min_length=1)
    passed: bool
    location: str | None = None
    action: str | None = None


class ArtifactDescriptor(StrictPayload):
    logical_name: str = Field(min_length=1)
    relative_path: str = Field(min_length=1)
    size_bytes: int = Field(ge=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class QualityReportPayload(StrictPayload):
    automated_passed: bool
    checks: tuple[QualityCheck, ...] = Field(min_length=1)
    package_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    missing_evidence: tuple[str, ...] = ()
    required_signers: tuple[str, ...] = ()
    generated_at: datetime
    artifacts: tuple[ArtifactDescriptor, ArtifactDescriptor]

    @model_validator(mode="after")
    def validate_summary(self) -> Self:
        if self.automated_passed != all(item.passed for item in self.checks):
            raise ValueError("quality summary does not match checks")
        return self


class DeliveryArchiveParameters(StrictPayload):
    quality_report: QualityReportPayload
    evidence: tuple[str, ...] = ()
    signatures: dict[str, str] = Field(default_factory=dict)


class DeliveryDecisionPayload(StrictPayload):
    decision: Literal["archived", "blocked"]
    reasons: tuple[str, ...] = ()
    package_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    archive_id: str | None = None
    archive: ArtifactDescriptor | None = None
    signed_by: tuple[str, ...] = ()
    generated_at: datetime

    @model_validator(mode="after")
    def validate_archive(self) -> Self:
        if self.decision == "archived" and (self.archive is None or self.archive_id is None):
            raise ValueError("archived delivery requires immutable archive identity")
        if self.decision == "blocked" and self.archive is not None:
            raise ValueError("blocked delivery cannot publish an archive")
        return self
