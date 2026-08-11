from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator


class MaterialModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class OutlineMode(StrEnum):
    NONE = "none"
    GENERATED = "generated"
    SELECTED = "selected"
    MERGED = "merged"


class MergePolicy(StrEnum):
    MANUAL = "manual"
    APPEND = "append"
    CHAPTER_MATCH = "chapter_match"


class MaterialDocumentRef(MaterialModel):
    document_id: UUID = Field(default_factory=uuid4)
    asset_id: UUID | None = None
    source_ref: str = Field(min_length=1, max_length=500)
    title: str = Field(min_length=1, max_length=300)
    role: Literal["outline", "reference", "transcript", "notes", "unknown"] = "reference"
    enabled: bool = True

    @model_validator(mode="after")
    def validate_ref(self) -> MaterialDocumentRef:
        path = Path(self.source_ref)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("material source ref must be relative")
        return self


class MaterialPresentationRef(MaterialModel):
    presentation_id: UUID = Field(default_factory=uuid4)
    asset_id: UUID | None = None
    source_ref: str = Field(min_length=1, max_length=500)
    title: str = Field(min_length=1, max_length=300)
    enabled: bool = True
    page_count: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_ref(self) -> MaterialPresentationRef:
        path = Path(self.source_ref)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("presentation source ref must be relative")
        return self


class MaterialPageRef(MaterialModel):
    material_page_id: UUID = Field(default_factory=uuid4)
    source_asset_id: UUID | None = None
    source_ref: str = Field(min_length=1, max_length=500)
    order: int = Field(ge=0)
    title: str = Field(default="未命名页面", max_length=300)
    section_id: UUID | None = None
    enabled: bool = True
    visual_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    text_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_ref(self) -> MaterialPageRef:
        path = Path(self.source_ref)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("page source ref must be relative")
        return self


class MaterialSection(MaterialModel):
    section_id: UUID = Field(default_factory=uuid4)
    order: int = Field(ge=0)
    title: str = Field(min_length=1, max_length=300)
    enabled: bool = True
    page_ids: list[UUID] = Field(default_factory=list)


class MaterialCollection(MaterialModel):
    schema_version: Literal["1.0"] = "1.0"
    collection_id: UUID = Field(default_factory=uuid4)
    revision: int = Field(default=1, ge=1)
    project_id: UUID
    documents: list[MaterialDocumentRef] = Field(default_factory=list)
    presentations: list[MaterialPresentationRef] = Field(default_factory=list)
    sections: list[MaterialSection] = Field(default_factory=list)
    page_sequence: list[MaterialPageRef] = Field(default_factory=list)
    outline_mode: OutlineMode = OutlineMode.NONE
    merge_policy: MergePolicy = MergePolicy.MANUAL
    content_hash: str = ""

    @model_validator(mode="after")
    def validate_collection(self) -> MaterialCollection:
        page_ids = {page.material_page_id for page in self.page_sequence}
        if len(page_ids) != len(self.page_sequence):
            raise ValueError("material page ids must be unique")
        section_ids = {section.section_id for section in self.sections}
        if len(section_ids) != len(self.sections):
            raise ValueError("material section ids must be unique")
        for section in self.sections:
            if any(page_id not in page_ids for page_id in section.page_ids):
                raise ValueError("section references an unknown page")
        if any(
            page.section_id is not None and page.section_id not in section_ids
            for page in self.page_sequence
        ):
            raise ValueError("page references an unknown section")
        return self

    def with_content_hash(self) -> MaterialCollection:
        payload = self.model_dump(mode="json", exclude={"content_hash", "revision"})
        digest = hashlib.sha256(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
                "utf-8"
            )
        ).hexdigest()
        return self.model_copy(update={"content_hash": digest})


class MaterialCollectionCommand(MaterialModel):
    command_id: UUID = Field(default_factory=uuid4)
    expected_revision: int = Field(ge=1)
    kind: Literal[
        "reorder_pages",
        "reorder_sections",
        "merge_sections",
        "split_section",
        "replace_page",
        "disable_page",
    ]
    payload: dict[str, Any] = Field(default_factory=dict)


class MaterialSyncPreview(MaterialModel):
    collection_revision: int
    timeline_revision: int | None = None
    added_page_ids: list[UUID] = Field(default_factory=list)
    moved_page_ids: list[UUID] = Field(default_factory=list)
    replaced_page_ids: list[UUID] = Field(default_factory=list)
    disabled_page_ids: list[UUID] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
