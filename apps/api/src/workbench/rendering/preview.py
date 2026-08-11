from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .hashing import sha256_json
from .models import AffectedRange, RenderGraphV2


class PreviewRangeError(ValueError):
    """Raised when an authoritative preview range cannot be rendered."""


class RenderGraphPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start_us: int = Field(ge=0)
    end_us: int = Field(gt=0)
    preset: Literal["interactive", "authoritative"] = "authoritative"
    runtime_version: str = Field(default="rendergraph-v2", min_length=1, max_length=80)


class RenderGraphPreviewPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    graph_id: str
    graph_hash: str
    start_us: int = Field(ge=0)
    end_us: int = Field(gt=0)
    preset: Literal["interactive", "authoritative"]
    cache_key: str = Field(pattern=r"^[0-9a-f]{64}$")
    affected_ranges: list[AffectedRange] = Field(default_factory=list)


def build_preview_plan(
    graph: RenderGraphV2, request: RenderGraphPreviewRequest
) -> RenderGraphPreviewPlan:
    if request.end_us <= request.start_us:
        raise PreviewRangeError("preview end must be later than start")
    if request.end_us > graph.duration_us:
        raise PreviewRangeError("preview range exceeds graph duration")
    affected = [
        item
        for item in graph.affected_ranges
        if item.start_us < request.end_us and item.end_us > request.start_us
    ]
    cache_key = sha256_json(
        {
            "graph_hash": graph.graph_hash,
            "start_us": request.start_us,
            "end_us": request.end_us,
            "preset": request.preset,
            "runtime_version": request.runtime_version,
        }
    )
    return RenderGraphPreviewPlan(
        graph_id=str(graph.graph_id),
        graph_hash=graph.graph_hash,
        start_us=request.start_us,
        end_us=request.end_us,
        preset=request.preset,
        cache_key=cache_key,
        affected_ranges=affected,
    )
