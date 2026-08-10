from __future__ import annotations

from pathlib import Path
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class TextSpan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    bbox: tuple[float, float, float, float]
    confidence: float | None = Field(default=None, ge=0, le=1)
    needs_confirmation: bool = False


class PageExtraction(BaseModel):
    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    id: UUID
    order: int = Field(ge=1)
    text: str = ""
    title: str | None = None
    spans: list[TextSpan] = Field(default_factory=list)
    preview_path: Path | None = None
    width: int | None = Field(default=None, ge=1)
    height: int | None = Field(default=None, ge=1)
    hidden: bool = False
    rotation: int = 0
    needs_confirmation: bool = False
    extraction_method: Literal["pptx", "pdf_text", "ocr", "image"]
    source_ref: str


class PreviewBuildResult(BaseModel):
    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    engine: str
    pages: list[PageExtraction]
