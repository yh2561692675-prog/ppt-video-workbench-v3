from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from workbench.effects.schema import EffectPlanV2


class EffectContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EffectProjectPolicy(EffectContractModel):
    aspect_ratio: Literal["16:9", "9:16"] = "16:9"
    default_strength: float = Field(default=0.65, ge=0, le=1)
    automatic_generation_enabled: bool = True
    catalog_version: str = "effect-catalog-v2"
    presenter_enabled: bool = False
    presenter_asset_id: str | None = None
    presenter_anchor: Literal["bottom-left", "bottom-right"] = "bottom-right"


class EffectPlanRecord(EffectContractModel):
    revision: int = Field(ge=1)
    plan: EffectPlanV2
    plan_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    input_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    source: Literal["automatic", "manual", "migrated", "fallback"]
    status: Literal["ready", "fallback", "stale", "invalid"]
    locked: bool = False
    decision_reasons: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0, le=1)
    validation_codes: list[str] = Field(default_factory=list)
    updated_at: datetime


def calculate_plan_hash(plan: EffectPlanV2) -> str:
    encoded = json.dumps(
        plan.model_dump(mode="json"), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def validate_record_hash(record: EffectPlanRecord) -> EffectPlanRecord:
    expected = calculate_plan_hash(record.plan)
    if record.plan_hash != expected:
        raise ValueError("plan_hash does not match plan")
    return record
