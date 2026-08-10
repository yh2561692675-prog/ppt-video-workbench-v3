from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from workbench.domain.effects import EffectPlanRecord, calculate_plan_hash

from .fingerprint import calculate_input_fingerprint
from .schema import (
    EffectPlanV2,
    ProgressiveRevealPayload,
    StatCounterPayload,
)

PlanStatus = Literal["ready", "fallback"]
PlanSource = Literal["automatic", "fallback"]


class EffectPlanningInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page_id: str = Field(min_length=1)
    page_type: str = Field(default="content", min_length=1)
    duration_ms: int = Field(gt=0)
    title: str = ""
    text: str = ""
    cue_texts: list[str] = Field(default_factory=list, max_length=15)
    aspect_ratio: Literal["16:9", "9:16"] = "16:9"
    default_strength: float = Field(default=0.65, ge=0, le=1)
    catalog_version: str = "effect-catalog-v2"
    source_path: Path | None = None


class EffectPlanner:
    def plan(self, value: EffectPlanningInput) -> EffectPlanRecord:
        fingerprint = calculate_input_fingerprint(value)
        plan, status, source, reasons, confidence = self._build_plan(value)
        return EffectPlanRecord(
            revision=1,
            plan=plan,
            plan_hash=calculate_plan_hash(plan),
            input_fingerprint=fingerprint,
            source=source,
            status=status,
            decision_reasons=reasons,
            confidence=confidence,
            updated_at=datetime.now(UTC),
        )

    def reconcile(
        self,
        value: EffectPlanningInput,
        existing: EffectPlanRecord | None,
        *,
        force: bool = False,
    ) -> EffectPlanRecord:
        fingerprint = calculate_input_fingerprint(value)
        if existing is not None and existing.locked and existing.input_fingerprint != fingerprint:
            return existing.model_copy(update={"status": "stale"})
        if existing is not None and existing.input_fingerprint == fingerprint and not force:
            return existing
        generated = self.plan(value)
        if existing is not None:
            generated = generated.model_copy(update={"revision": existing.revision + 1})
        return generated

    def _build_plan(
        self, value: EffectPlanningInput
    ) -> tuple[EffectPlanV2, PlanStatus, PlanSource, list[str], float]:
        content = "\n".join(
            part for part in [value.title, value.text, *value.cue_texts] if part
        ).strip()
        if not content:
            return (
                EffectPlanV2(
                    page_id=value.page_id,
                    page_type=value.page_type,
                    duration_ms=value.duration_ms,
                    aspect_ratio=value.aspect_ratio,
                    template="SafeSlide",
                ),
                "fallback",
                "fallback",
                ["empty_page_content"],
                0.0,
            )

        number_match = re.search(r"-?\d+(?:\.\d+)?", content)
        if number_match:
            value_number = float(number_match.group(0))
            plan = EffectPlanV2(
                page_id=value.page_id,
                page_type=value.page_type,
                duration_ms=value.duration_ms,
                aspect_ratio=value.aspect_ratio,
                template="StatCounter",
                template_payload=StatCounterPayload(
                    label=value.title or "指标",
                    start=0,
                    end=value_number,
                ),
            )
            return plan, "ready", "automatic", ["numeric_content"], 0.8

        items = [
            item.strip() for item in (*value.cue_texts, *value.text.splitlines()) if item.strip()
        ]
        items = list(dict.fromkeys(items))[:6]
        if items:
            plan = EffectPlanV2(
                page_id=value.page_id,
                page_type=value.page_type,
                duration_ms=value.duration_ms,
                aspect_ratio=value.aspect_ratio,
                template="ProgressiveReveal",
                template_payload=ProgressiveRevealPayload(items=items),
            )
            return plan, "ready", "automatic", ["structured_text"], 0.75
        return (
            EffectPlanV2(
                page_id=value.page_id,
                page_type=value.page_type,
                duration_ms=value.duration_ms,
                aspect_ratio=value.aspect_ratio,
                template="SafeSlide",
            ),
            "fallback",
            "fallback",
            ["payload_empty"],
            0.0,
        )
