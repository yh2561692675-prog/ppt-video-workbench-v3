from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ConfirmationModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Confirmation(ConfirmationModel):
    id: UUID
    page_id: UUID
    revision_id: UUID
    actor: str = Field(min_length=1)
    confirmed_at: datetime
    conflict_resolution: str | None = None


class GateReason(ConfirmationModel):
    code: str
    message: str
    page_id: UUID
    action: str


class GateResult(ConfirmationModel):
    allowed: bool
    reasons: list[GateReason] = Field(default_factory=list)
