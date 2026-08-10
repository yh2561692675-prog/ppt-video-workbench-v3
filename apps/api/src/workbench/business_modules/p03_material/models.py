from __future__ import annotations

from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")


class InlineMaterial(StrictPayload):
    name: str = Field(min_length=1, max_length=255)
    content_base64: str = Field(min_length=1)


class MaterialIngestParameters(StrictPayload):
    files: tuple[InlineMaterial, ...] = ()
    input_names: tuple[str, ...] = ()


class MaterialSource(StrictPayload):
    original_name: str = Field(min_length=1, max_length=255)
    safe_name: str = Field(min_length=1, max_length=180)
    kind: Literal["docx", "pptx", "pdf", "image"]
    size_bytes: int = Field(ge=1, le=500 * 1024 * 1024)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    image_order: int | None = Field(default=None, ge=1)
    relative_path: str = Field(min_length=1, max_length=255)


class MaterialReorderParameters(StrictPayload):
    sources: tuple[MaterialSource, ...] = Field(min_length=1)
    ordered_names: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_order(self) -> Self:
        source_names = [item.safe_name for item in self.sources]
        if len(source_names) != len(set(source_names)):
            raise ValueError("material sources contain duplicate safe names")
        if len(self.ordered_names) != len(set(self.ordered_names)):
            raise ValueError("ordered_names contains duplicates")
        if set(source_names) != set(self.ordered_names):
            raise ValueError("ordered_names must contain every source exactly once")
        return self


class MaterialSourcesPayload(StrictPayload):
    operation: Literal["ingest", "reorder"]
    sources: tuple[MaterialSource, ...]
    ordered_names: tuple[str, ...]

    @model_validator(mode="after")
    def validate_sources(self) -> Self:
        names = [item.safe_name for item in self.sources]
        if len(names) != len(set(names)):
            raise ValueError("material payload contains duplicate safe names")
        if tuple(names) != self.ordered_names:
            raise ValueError("ordered_names must match source payload order")
        return self
