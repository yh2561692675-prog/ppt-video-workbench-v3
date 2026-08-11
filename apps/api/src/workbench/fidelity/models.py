from __future__ import annotations

from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class FidelityLevel(StrEnum):
    F0 = "F0"
    F1 = "F1"
    F2 = "F2"
    F3 = "F3"


class FidelityRenderer(StrEnum):
    PYTHON = "python"
    LIBREOFFICE = "libreoffice"
    POWERPOINT = "powerpoint"
    NATIVE_CAPTURE = "native_capture"


class MotionSupport(StrEnum):
    SUPPORTED = "supported"
    DEGRADED = "degraded"
    NATIVE_CAPTURE_REQUIRED = "native_capture_required"
    UNSUPPORTED = "unsupported"


class FidelityIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1, max_length=100)
    message: str = Field(min_length=1, max_length=500)
    blocking: bool = False
    action: str = Field(min_length=1, max_length=500)


class SlideShape(BaseModel):
    model_config = ConfigDict(extra="forbid")

    shape_id: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=200)
    kind: str = Field(min_length=1, max_length=80)
    z_order: int = Field(ge=0)
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    width: float = Field(ge=0, le=1)
    height: float = Field(ge=0, le=1)
    rotation: float = 0
    opacity: float = Field(default=1, ge=0, le=1)
    text: str = ""
    text_style: dict[str, str | int | float | bool] = Field(default_factory=dict)
    resource_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")


class MotionCue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cue_id: UUID
    shape_ids: list[str] = Field(min_length=1)
    trigger: Literal["with_previous", "after_previous", "on_click"] = "after_previous"
    sequence: int = Field(ge=0)
    start_ms: int = Field(ge=0)
    duration_ms: int = Field(gt=0)
    entrance: str | None = None
    emphasis: str | None = None
    exit: str | None = None
    easing: str = "ease_in_out"
    direction: str | None = None
    repeat: int = Field(default=1, ge=1)
    support: MotionSupport = MotionSupport.SUPPORTED
    source_effect: str | None = None


class SlideScene(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slide_id: UUID
    page_index: int = Field(ge=1)
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    background: str = "#ffffff"
    shapes: list[SlideShape] = Field(default_factory=list)
    motion_cues: list[MotionCue] = Field(default_factory=list)
    notes: str = ""


class SlideFidelityPage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page_id: UUID
    page_index: int = Field(ge=1)
    level: FidelityLevel
    renderer: FidelityRenderer
    scene: SlideScene
    preview_path: str | None = None
    issues: list[FidelityIssue] = Field(default_factory=list)
    downgrade_reason: str | None = None
    input_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class SlideFidelityManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    source_path: str
    source_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    pages: list[SlideFidelityPage]
    capability: dict[str, bool] = Field(default_factory=dict)
    scanner_version: str = "fidelity-scanner-v1"
    manifest_hash: str = ""


class FidelityPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    preferred_renderer: Literal["auto", "powerpoint", "libreoffice", "python"] = "auto"
    allow_static_fallback: bool = True
    require_animation_support: bool = False
    capture_unsupported_animations: bool = False
    max_slide_count: int = Field(default=500, gt=0)
    max_xml_bytes: int = Field(default=50 * 1024 * 1024, gt=0)


class FidelityJobRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pptx_path: str = Field(min_length=1, max_length=300)
    output_dir: str = Field(default="fidelity", min_length=1, max_length=300)
    policy: FidelityPolicy = Field(default_factory=FidelityPolicy)


class FidelityJobRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: UUID
    status: Literal["running", "succeeded", "degraded", "failed"]
    manifest: SlideFidelityManifest | None = None
    error_code: str | None = None
    error: str | None = None
