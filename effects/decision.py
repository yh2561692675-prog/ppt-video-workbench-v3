from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Mapping, Sequence

from .backgrounds import choose_background
from .template_catalog import get_template


Strength = Literal["restrained", "standard", "enhanced"]


@dataclass(frozen=True)
class EffectDecision:
    template: str
    strength: Strength
    background: str
    camera: str
    transition: str
    reasons: tuple[str, ...]
    confidence: float
    manual_lock: bool


def recommend_effect(
    page_model: Mapping[str, object],
    cues: Sequence[object],
    policy: Mapping[str, object] | None = None,
) -> EffectDecision:
    del cues
    policy = policy or {}
    manual_template = page_model.get("manual_template")
    manual_lock = bool(page_model.get("manual_lock", False))
    if manual_lock and isinstance(manual_template, str) and get_template(manual_template):
        template = manual_template
        reasons = ("manual_lock",)
        confidence = 1.0
    else:
        template, reason, confidence = _select_template(page_model)
        reasons = (reason,)

    strength = _strength(page_model, policy)
    semantic = _semantic(page_model)
    background = choose_background(semantic, str(policy.get("project_style", "education")))
    camera = "push" if template in {"StatCounter", "ChartNarration"} else "static"
    transition = "crossfade"
    return EffectDecision(
        template=template,
        strength=strength,
        background=background,
        camera=camera,
        transition=transition,
        reasons=reasons,
        confidence=confidence,
        manual_lock=manual_lock,
    )


def _select_template(page: Mapping[str, object]) -> tuple[str, str, float]:
    modules = {str(item).casefold() for item in _list_value(page.get("modules"))}
    metrics = _list_value(page.get("metrics"))
    series = _list_value(page.get("series"))
    if len(metrics) >= 2:
        return "StatCounter", "detected_multiple_metrics", 0.96
    if series or page.get("chart_type"):
        return "ChartNarration", "detected_chart_series", 0.94
    if page.get("map") or _list_value(page.get("cities")):
        return "MapHighlight", "detected_geographic_entities", 0.92
    if {"advantages", "risks"}.issubset(modules) or {"pros", "cons"}.issubset(modules):
        return "CompareMode", "detected_comparison_roles", 0.91
    density = float(page.get("text_density", 0.0) or 0.0)
    text_length = len(str(page.get("text", "")))
    if density >= 0.75 or text_length >= 600:
        return "FocusSpotlight", "dense_text_requires_restrained_motion", 0.9
    if str(page.get("page_type", "")).casefold() in {"chapter", "cover"}:
        return "ChapterCurtain", "chapter_boundary", 0.88
    return "SafeSlide", "no_high_confidence_semantic_match", 0.55


def _strength(page: Mapping[str, object], policy: Mapping[str, object]) -> Strength:
    explicit = policy.get("strength")
    if explicit in {"restrained", "standard", "enhanced"}:
        return explicit  # type: ignore[return-value]
    density = float(page.get("text_density", 0.0) or 0.0)
    if density >= 0.75 or len(str(page.get("text", ""))) >= 600:
        return "restrained"
    if str(page.get("page_type", "")).casefold() in {"chapter", "cover"}:
        return "enhanced"
    return "standard"


def _semantic(page: Mapping[str, object]) -> str:
    if "risk" in {str(item).casefold() for item in _list_value(page.get("modules"))}:
        return "risk"
    if str(page.get("page_type", "")).casefold() in {"conclusion", "recommendation"}:
        return "conclusion"
    return str(page.get("semantic", "fact"))


def _list_value(value: object) -> list[object]:
    return list(value) if isinstance(value, (list, tuple, set)) else []
