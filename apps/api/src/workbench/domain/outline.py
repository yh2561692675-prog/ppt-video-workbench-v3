from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class OutlineBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["heading", "paragraph", "table"]
    order: int = Field(ge=1)
    level: int | None = Field(default=None, ge=1, le=9)
    text: str
    table_cells: list[list[str]] | None = None
    source_ref: str


class OutlineDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_name: str
    blocks: list[OutlineBlock]


class OutlineArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_sha256: str
    cache_key: str
    document: OutlineDocument
