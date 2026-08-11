from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator


class OccupancyContract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class NormalizedRect(OccupancyContract):
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    width: float = Field(gt=0, le=1)
    height: float = Field(gt=0, le=1)

    @model_validator(mode="after")
    def validate_bounds(self) -> NormalizedRect:
        if self.x + self.width > 1.000001 or self.y + self.height > 1.000001:
            raise ValueError("occupancy rectangle exceeds normalized canvas")
        return self


class PageOccupancyMap(OccupancyContract):
    critical: list[NormalizedRect] = Field(default_factory=list)
    content: list[NormalizedRect] = Field(default_factory=list)
    captions: list[NormalizedRect] = Field(default_factory=list)
    preferred_region: str | None = None


def overlap_area(left: NormalizedRect, right: NormalizedRect) -> float:
    width = max(0.0, min(left.x + left.width, right.x + right.width) - max(left.x, right.x))
    height = max(0.0, min(left.y + left.height, right.y + right.height) - max(left.y, right.y))
    return width * height


def overlap_ratio(rect: NormalizedRect, occupied: list[NormalizedRect]) -> float:
    if not occupied:
        return 0.0
    return min(1.0, sum(overlap_area(rect, item) for item in occupied) / (rect.width * rect.height))
