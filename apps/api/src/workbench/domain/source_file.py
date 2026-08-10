from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class SourceKind(StrEnum):
    DOCX = "docx"
    PPTX = "pptx"
    PDF = "pdf"
    IMAGE = "image"


class SourceFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    kind: SourceKind
    original_name: str = Field(min_length=1)
    safe_name: str = Field(min_length=1)
    copied_path: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    size: int = Field(ge=0)
    modified_at: datetime
    image_order: int | None = Field(default=None, ge=1)
