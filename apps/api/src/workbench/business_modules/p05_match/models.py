from __future__ import annotations

from typing import Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from workbench.domain.extraction import PageExtraction
from workbench.domain.matching import PageMatch
from workbench.domain.outline import OutlineDocument


class StrictPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ManualBinding(StrictPayload):
    page_id: UUID
    selected_outline_ref: str = Field(min_length=1, max_length=512)


class ContentMatchParameters(StrictPayload):
    outline: OutlineDocument
    pages: tuple[PageExtraction, ...] = Field(min_length=1)
    manual_bindings: tuple[ManualBinding, ...] = ()

    @model_validator(mode="after")
    def validate_identity(self) -> Self:
        page_ids = [item.id for item in self.pages]
        if len(page_ids) != len(set(page_ids)):
            raise ValueError("matching pages contain duplicate ids")
        binding_ids = [item.page_id for item in self.manual_bindings]
        if len(binding_ids) != len(set(binding_ids)):
            raise ValueError("manual bindings contain duplicate page ids")
        if not set(binding_ids).issubset(page_ids):
            raise ValueError("manual binding references an unknown page")
        return self


class PageMatchesPayload(StrictPayload):
    matches: tuple[PageMatch, ...]
    conflict_count: int = Field(ge=0)
    confirmation_count: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_summary(self) -> Self:
        if self.conflict_count != sum(len(item.conflicts) for item in self.matches):
            raise ValueError("conflict_count does not match page matches")
        if self.confirmation_count != sum(item.needs_confirmation for item in self.matches):
            raise ValueError("confirmation_count does not match page matches")
        for item in self.matches:
            candidate_refs = {candidate.outline_ref for candidate in item.candidates}
            if (
                item.selected_outline_ref is not None
                and item.selected_outline_ref not in candidate_refs
            ):
                raise ValueError("selected outline ref is not present in candidates")
        return self
