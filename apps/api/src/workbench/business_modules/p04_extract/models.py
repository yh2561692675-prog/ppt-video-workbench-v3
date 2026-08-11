from __future__ import annotations

import hashlib
import json
from typing import Any, Literal, Self

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

    @model_validator(mode="before")
    @classmethod
    def normalize_legacy_result(cls, value: Any) -> Any:
        """Accept result payloads written before cache/page metadata was added.

        The worker always emits the complete v1 shape.  This migration is only
        for projecting older, already-persisted results into the current
        manifest without weakening the serialized output contract.
        """

        if not isinstance(value, dict):
            return value
        normalized = dict(value)
        pages = normalized.get("pages", ())
        if "page_count" not in normalized and isinstance(pages, (list, tuple)):
            normalized["page_count"] = len(pages)
        if "cache_key" not in normalized:
            canonical = json.dumps(
                {
                    "source_name": normalized.get("source_name"),
                    "outline": normalized.get("outline"),
                    "pages": pages,
                    "page_count": normalized.get("page_count"),
                },
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                default=str,
            )
            normalized["cache_key"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        return normalized

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

    @model_validator(mode="before")
    @classmethod
    def normalize_legacy_result(cls, value: Any) -> Any:
        """Fill fields introduced after the first P04 result format."""

        if not isinstance(value, dict):
            return value
        normalized = dict(value)
        normalized.setdefault("operation", "extract")
        if "page_count" not in normalized:
            documents = normalized.get("documents", ())
            if isinstance(documents, (list, tuple)):
                normalized["page_count"] = sum(
                    int(document.get("page_count", len(document.get("pages", ()))))
                    for document in documents
                    if isinstance(document, dict)
                )
        return normalized

    @model_validator(mode="after")
    def validate_page_count(self) -> Self:
        if self.page_count != sum(item.page_count for item in self.documents):
            raise ValueError("payload page_count does not match documents")
        return self
