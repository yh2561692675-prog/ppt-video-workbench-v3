from __future__ import annotations

from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from workbench.domain.extraction import PageExtraction
from workbench.domain.outline import OutlineDocument


class StrictPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")


class InlineDocument(StrictPayload):
    name: str = Field(min_length=1, max_length=255)
    content_base64: str = Field(min_length=1)


class DocumentExtractionParameters(StrictPayload):
    files: tuple[InlineDocument, ...] = ()
    input_names: tuple[str, ...] = ()
    ocr_policy: Literal["never", "auto", "always"] = "auto"


class ExtractedDocument(StrictPayload):
    source_name: str = Field(min_length=1, max_length=255)
    outline: OutlineDocument
    pages: tuple[PageExtraction, ...]
    page_count: int = Field(ge=0)
    cache_key: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_page_count(self) -> Self:
        if self.page_count != len(self.pages):
            raise ValueError("document page_count does not match pages")
        return self


class PreviewArtifact(StrictPayload):
    logical_name: str = Field(pattern=r"^[a-z][a-z0-9_.-]{1,63}$")
    relative_path: str = Field(min_length=1, max_length=1024)
    size_bytes: int = Field(ge=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class DocumentExtractionPayload(StrictPayload):
    operation: Literal["extract", "ocr"]
    documents: tuple[ExtractedDocument, ...]
    previews: tuple[PreviewArtifact, ...] = ()
    page_count: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_page_count(self) -> Self:
        if self.page_count != sum(item.page_count for item in self.documents):
            raise ValueError("payload page_count does not match documents")
        return self
