from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class MatchWeights(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page_order: float = 0.20
    title: float = 0.45
    keywords: float = 0.25
    body: float = 0.10


class MatchComponents(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page_order: float = Field(ge=0, le=1)
    title: float = Field(ge=0, le=1)
    keywords: float = Field(ge=0, le=1)
    body: float = Field(ge=0, le=1)


class MatchCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    outline_ref: str
    outline_title: str
    outline_text: str
    score: float = Field(ge=0, le=1)
    weights: MatchWeights
    components: MatchComponents


class PageMatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page_id: UUID
    page_order: int = Field(ge=1)
    page_title: str | None = None
    page_text: str = ""
    preview_path: str | None = None
    selected_outline_ref: str | None = None
    score: float = Field(ge=0, le=1)
    needs_confirmation: bool
    conflicts: list[str] = Field(default_factory=list)
    decision_source: Literal["deterministic_rules", "manual"]
    candidates: list[MatchCandidate] = Field(default_factory=list)


class MatchPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    matches: list[PageMatch]
