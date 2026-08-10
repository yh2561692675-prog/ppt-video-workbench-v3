from __future__ import annotations

import hashlib
import json
import math
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class EffectModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EffectCue(EffectModel):
    id: str = Field(min_length=1)
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)
    kind: str = Field(default="content", min_length=1)
    text: str = ""

    @model_validator(mode="after")
    def validate_range(self) -> EffectCue:
        if self.end_ms <= self.start_ms:
            raise ValueError("提示点结束时间必须晚于开始时间")
        return self


class EffectEvent(EffectModel):
    type: str = Field(min_length=1)
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)
    target: str | None = None
    intensity: float = Field(default=1.0, ge=0, le=1)

    @model_validator(mode="after")
    def validate_range(self) -> EffectEvent:
        if self.end_ms <= self.start_ms:
            raise ValueError("特效结束时间必须晚于开始时间")
        return self


class CameraPlan(EffectModel):
    mode: Literal["static", "push", "pan", "spotlight"] = "static"
    scale_start: float = Field(default=1.0, ge=1.0, le=1.08)
    scale_end: float = Field(default=1.0, ge=1.0, le=1.08)
    focus_x: float = Field(default=0.5, ge=0, le=1)
    focus_y: float = Field(default=0.5, ge=0, le=1)


class TransitionPlan(EffectModel):
    type: Literal["cut", "crossfade", "mask"] = "crossfade"
    duration_ms: int = Field(default=400, ge=0)


class PresenterCue(EffectModel):
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)
    position: Literal["top-left", "top-right", "bottom-left", "bottom-right"] = "bottom-right"
    reason: str = ""

    @model_validator(mode="after")
    def validate_range(self) -> PresenterCue:
        if self.end_ms <= self.start_ms:
            raise ValueError("真人提示点结束时间必须晚于开始时间")
        return self


class FallbackPlan(EffectModel):
    template: Literal["SafeSlide", "FocusSpotlight"] = "SafeSlide"
    reason: str | None = None


TemplateName = Literal[
    "ProgressiveReveal",
    "ChapterCurtain",
    "StatCounter",
    "ChartNarration",
    "CompareMode",
    "FocusSpotlight",
    "CardStack",
    "GaugeAndRatio",
    "PathBuilder",
    "TagMatrix",
    "RiskAlert",
    "MapHighlight",
    "SafeSlide",
]


class SafeSlidePayload(EffectModel):
    kind: Literal["safe_slide"] = "safe_slide"
    title: str = Field(default="", max_length=200)
    summary: str = Field(default="", max_length=1_000)


class ProgressiveRevealPayload(EffectModel):
    kind: Literal["progressive_reveal"] = "progressive_reveal"
    items: list[str] = Field(min_length=1, max_length=6)


class ChapterCurtainPayload(EffectModel):
    kind: Literal["chapter_curtain"] = "chapter_curtain"
    chapter_number: str = Field(min_length=1, max_length=20)
    title: str = Field(min_length=1, max_length=200)
    palette: str = Field(default="tech_blue", min_length=1, max_length=40)


class StatCounterPayload(EffectModel):
    kind: Literal["stat_counter"] = "stat_counter"
    label: str = Field(min_length=1, max_length=120)
    start: float
    end: float
    format: str = Field(default="number", min_length=1, max_length=40)

    @model_validator(mode="after")
    def validate_numbers(self) -> StatCounterPayload:
        if not math.isfinite(self.start) or not math.isfinite(self.end):
            raise ValueError("计数器数值必须为有限数")
        return self


class ChartNarrationPayload(EffectModel):
    kind: Literal["chart_narration"] = "chart_narration"
    series: list[dict[str, float | str]] = Field(min_length=2, max_length=12)
    cue_points: list[int] = Field(default_factory=list, max_length=12)
    annotation: str = Field(default="", max_length=240)


class CompareModePayload(EffectModel):
    kind: Literal["compare_mode"] = "compare_mode"
    left: str = Field(min_length=1, max_length=500)
    right: str = Field(min_length=1, max_length=500)


class FocusSpotlightPayload(EffectModel):
    kind: Literal["focus_spotlight"] = "focus_spotlight"
    targets: list[dict[str, float | str]] = Field(min_length=1, max_length=3)
    label: str = Field(default="", max_length=160)


class CardStackPayload(EffectModel):
    kind: Literal["card_stack"] = "card_stack"
    cards: list[str] = Field(min_length=1, max_length=3)


class GaugeAndRatioPayload(EffectModel):
    kind: Literal["gauge_and_ratio"] = "gauge_and_ratio"
    label: str = Field(min_length=1, max_length=120)
    value: float = Field(ge=0, le=1)


class PathBuilderPayload(EffectModel):
    kind: Literal["path_builder"] = "path_builder"
    nodes: list[str] = Field(min_length=2, max_length=6)


class TagMatrixPayload(EffectModel):
    kind: Literal["tag_matrix"] = "tag_matrix"
    tags: list[str] = Field(min_length=2, max_length=15)


class RiskAlertPayload(EffectModel):
    kind: Literal["risk_alert"] = "risk_alert"
    title: str = Field(min_length=1, max_length=160)
    reason: str = Field(min_length=1, max_length=500)


class MapHighlightPayload(EffectModel):
    kind: Literal["map_highlight"] = "map_highlight"
    points: list[dict[str, float | str]] = Field(min_length=1, max_length=5)
    conclusion: str = Field(default="", max_length=300)


TemplatePayload = Annotated[
    SafeSlidePayload
    | ProgressiveRevealPayload
    | ChapterCurtainPayload
    | StatCounterPayload
    | ChartNarrationPayload
    | CompareModePayload
    | FocusSpotlightPayload
    | CardStackPayload
    | GaugeAndRatioPayload
    | PathBuilderPayload
    | TagMatrixPayload
    | RiskAlertPayload
    | MapHighlightPayload,
    Field(discriminator="kind"),
]

_TEMPLATE_KINDS = {
    "ProgressiveReveal": "progressive_reveal",
    "ChapterCurtain": "chapter_curtain",
    "StatCounter": "stat_counter",
    "ChartNarration": "chart_narration",
    "CompareMode": "compare_mode",
    "FocusSpotlight": "focus_spotlight",
    "CardStack": "card_stack",
    "GaugeAndRatio": "gauge_and_ratio",
    "PathBuilder": "path_builder",
    "TagMatrix": "tag_matrix",
    "RiskAlert": "risk_alert",
    "MapHighlight": "map_highlight",
    "SafeSlide": "safe_slide",
}


class EffectPlanV2(EffectModel):
    schema_version: Literal["2.0"] = "2.0"
    page_id: str = Field(min_length=1)
    page_type: str = Field(min_length=1)
    duration_ms: int = Field(gt=0)
    aspect_ratio: Literal["16:9", "9:16"] = "16:9"
    rhythm_profile: Literal["steady", "standard", "compact", "enhanced"] = "steady"
    background_preset: Literal[
        "tech_blue", "risk_red", "warm_gold", "paper_grid", "regional_teal"
    ] = "tech_blue"
    template: TemplateName = "SafeSlide"
    template_payload: TemplatePayload = Field(default_factory=SafeSlidePayload)
    cues: list[EffectCue] = Field(default_factory=list)
    effects: list[EffectEvent] = Field(default_factory=list)
    camera: CameraPlan = Field(default_factory=CameraPlan)
    transition: TransitionPlan = Field(default_factory=TransitionPlan)
    presenter_cues: list[PresenterCue] = Field(default_factory=list)
    manual_lock: bool = False
    fallback: FallbackPlan = Field(default_factory=FallbackPlan)
    source_hashes: dict[str, str] = Field(default_factory=dict)
    migration_version: str | None = None
    legacy_payload_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_timeline_and_payload(self) -> EffectPlanV2:
        expected_kind = _TEMPLATE_KINDS[self.template]
        if self.template_payload.kind != expected_kind:
            raise ValueError(
                f"template {self.template} requires payload kind {expected_kind}"
            )
        ranges = [*self.cues, *self.effects, *self.presenter_cues]
        if any(item.end_ms > self.duration_ms for item in ranges):
            raise ValueError("特效时间轴不得超出页面时长")
        if self.transition.duration_ms > self.duration_ms:
            raise ValueError("转场时长不得超出页面时长")
        return self


def migrate_effect_plan(payload: dict[str, object]) -> EffectPlanV2:
    version = payload.get("schema_version")
    if version == "2.0":
        return EffectPlanV2.model_validate(payload)
    if version not in {"1.0", 1, None}:
        raise ValueError(f"不支持的特效计划版本: {version}")

    legacy_hash = hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()
    effects = payload.get("effects", [])
    if not isinstance(effects, list):
        raise ValueError("V1 特效计划的 effects 必须为数组")
    return EffectPlanV2.model_validate(
        {
            "schema_version": "2.0",
            "page_id": payload.get("page_id", "unknown-page"),
            "page_type": payload.get("page_type", "content"),
            "duration_ms": payload.get("duration_ms", 1),
            "aspect_ratio": payload.get("aspect_ratio", "16:9"),
            "rhythm_profile": "steady",
            "background_preset": "tech_blue",
            "template": payload.get("template", "SafeSlide"),
            "template_payload": payload.get(
                "template_payload", {"kind": "safe_slide", "title": "", "summary": ""}
            ),
            "cues": payload.get("cues", []),
            "effects": effects,
            "camera": payload.get("camera", {"mode": "static", "scale_start": 1, "scale_end": 1}),
            "transition": payload.get("transition", {"type": "crossfade", "duration_ms": 400}),
            "presenter_cues": payload.get("presenter_cues", []),
            "manual_lock": payload.get("manual_lock", False),
            "fallback": {"template": "SafeSlide", "reason": "V1 compatibility fallback"},
            "source_hashes": payload.get("source_hashes", {}),
            "migration_version": "v1-to-v2",
            "legacy_payload_hash": legacy_hash,
        }
    )


def _canonical_json(payload: dict[str, object]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


__all__ = [
    "EffectCue",
    "EffectEvent",
    "CameraPlan",
    "TransitionPlan",
    "PresenterCue",
    "FallbackPlan",
    "EffectPlanV2",
    "TemplateName",
    "TemplatePayload",
    "SafeSlidePayload",
    "ProgressiveRevealPayload",
    "ChapterCurtainPayload",
    "StatCounterPayload",
    "ChartNarrationPayload",
    "CompareModePayload",
    "FocusSpotlightPayload",
    "CardStackPayload",
    "GaugeAndRatioPayload",
    "PathBuilderPayload",
    "TagMatrixPayload",
    "RiskAlertPayload",
    "MapHighlightPayload",
    "migrate_effect_plan",
]
