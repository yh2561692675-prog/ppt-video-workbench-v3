from __future__ import annotations

from datetime import datetime
from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from workbench.narration.prompt_builder import NarrationDraft, PageContext


class StrictPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RevisionTarget(StrictPayload):
    page_id: UUID
    expected_revision_id: UUID | None = None
    expected_version: int = Field(default=0, ge=0)


class NarrationGenerateParameters(RevisionTarget):
    profile_id: UUID
    context: PageContext

    @model_validator(mode="after")
    def validate_page(self) -> Self:
        if self.context.page_id != self.page_id:
            raise ValueError("generation context page does not match revision target")
        return self


class NarrationAssignment(RevisionTarget):
    text: str = Field(min_length=1)
    author: str = Field(default="peripheral-import", min_length=1)
    source_refs: tuple[str, ...] = ()
    insufficiencies: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


class NarrationImportParameters(StrictPayload):
    assignments: tuple[NarrationAssignment, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_pages(self) -> Self:
        page_ids = [item.page_id for item in self.assignments]
        if len(page_ids) != len(set(page_ids)):
            raise ValueError("narration import contains duplicate pages")
        return self


class NarrationExportPage(StrictPayload):
    page_id: UUID
    page_order: int = Field(ge=1)
    page_title: str | None = None
    revision_id: UUID
    version: int = Field(ge=1)
    text: str = Field(min_length=1)
    confirmed: Literal[True]
    confirmed_by: str = Field(min_length=1)
    confirmed_at: datetime


class NarrationExportParameters(StrictPayload):
    project_name: str = Field(min_length=1, max_length=120)
    pages: tuple[NarrationExportPage, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_order(self) -> Self:
        orders = [item.page_order for item in self.pages]
        if len(orders) != len(set(orders)) or orders != sorted(orders):
            raise ValueError("narration export pages must have unique ascending order")
        return self


class ProjectedNarrationRevision(StrictPayload):
    id: UUID
    page_id: UUID
    version: int = Field(ge=1)
    text: str = Field(min_length=1)
    author: str = Field(min_length=1)
    source_refs: tuple[str, ...] = ()
    insufficiencies: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    parent_revision_id: UUID | None = None
    created_at: datetime
    character_count: int = Field(ge=1)
    estimated_duration_seconds: float = Field(gt=0)


class NarrationRevisionsPayload(StrictPayload):
    operation: Literal["generate", "import"]
    revisions: tuple[ProjectedNarrationRevision, ...] = Field(min_length=1)
    profile_id: UUID | None = None
    profile_base_url_digest: str | None = None
    profile_model: str | None = None

    @model_validator(mode="after")
    def validate_usage(self) -> Self:
        usage = (self.profile_id, self.profile_base_url_digest, self.profile_model)
        if self.operation == "generate" and any(item is None for item in usage):
            raise ValueError("generated narration requires public profile usage metadata")
        if self.operation == "import" and any(item is not None for item in usage):
            raise ValueError("imported narration cannot contain profile usage metadata")
        return self


class NarrationDocxPayload(StrictPayload):
    operation: Literal["export"]
    relative_path: str = Field(min_length=1)
    size_bytes: int = Field(ge=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    page_count: int = Field(ge=1)


def assignment_from_draft(
    target: NarrationGenerateParameters,
    draft: NarrationDraft,
) -> NarrationAssignment:
    return NarrationAssignment(
        page_id=target.page_id,
        expected_revision_id=target.expected_revision_id,
        expected_version=target.expected_version,
        text=draft.text,
        author="AI draft",
        source_refs=tuple(draft.source_refs),
        insufficiencies=tuple(draft.insufficiencies),
        warnings=tuple(draft.warnings),
    )
