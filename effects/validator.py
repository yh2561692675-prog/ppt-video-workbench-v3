from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from .schema import EffectPlanV2


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    message: str
    blocking: bool = True


@dataclass(frozen=True)
class ValidationReport:
    issues: tuple[ValidationIssue, ...] = ()

    @property
    def blocking(self) -> bool:
        return any(issue.blocking for issue in self.issues)


def validate_effect_plan(plan: Mapping[str, object] | EffectPlanV2) -> ValidationReport:
    """Run deterministic safety checks before an effect plan is rendered."""
    data = plan.model_dump(mode="python") if isinstance(plan, EffectPlanV2) else dict(plan)
    issues: list[ValidationIssue] = []

    if data.get("camera_count", 1) != 1:
        issues.append(
            ValidationIssue("two_main_cameras", "A page must have exactly one main camera.")
        )

    caption = data.get("caption_rect")
    occupied = data.get("occupied_rects", [])
    if (
        isinstance(caption, Mapping)
        and isinstance(occupied, Sequence)
        and any(_overlaps(caption, rect) for rect in occupied if isinstance(rect, Mapping))
    ):
        issues.append(ValidationIssue("caption_overlap", "Caption rail overlaps occupied content."))

    speech_start = data.get("speech_start_ms")
    cues = data.get("cues", [])
    if (
        isinstance(speech_start, (int, float))
        and isinstance(cues, Sequence)
        and any(isinstance(cue, Mapping) and cue.get("start_ms", 0) < speech_start for cue in cues)
    ):
        issues.append(ValidationIssue("cue_before_speech", "Cue starts before speech is ready."))

    transition_duration = data.get("transition_duration_ms")
    if isinstance(transition_duration, (int, float)) and transition_duration > 600:
        issues.append(
            ValidationIssue("transition_too_long", "Transition exceeds the 600 ms safety limit.")
        )
    elif isinstance(data.get("transition"), Mapping):
        nested_duration = data["transition"].get("duration_ms", 0)
        if isinstance(nested_duration, (int, float)) and nested_duration > 600:
            issues.append(
                ValidationIssue(
                    "transition_too_long", "Transition exceeds the 600 ms safety limit."
                )
            )

    effects = data.get("effects", [])
    if isinstance(effects, Sequence) and any(
        isinstance(effect, Mapping)
        and (effect.get("loop") is True or effect.get("type") == "infinite_loop")
        for effect in effects
    ):
        issues.append(
            ValidationIssue("infinite_loop", "Infinite or unbounded loops are not allowed.")
        )

    return ValidationReport(tuple(issues))


def _overlaps(left: Mapping[str, object], right: Mapping[str, object]) -> bool:
    try:
        lx, ly = float(left["x"]), float(left["y"])
        lw, lh = float(left["width"]), float(left["height"])
        rx, ry = float(right["x"]), float(right["y"])
        rw, rh = float(right["width"]), float(right["height"])
    except (KeyError, TypeError, ValueError):
        return False
    return lx < rx + rw and rx < lx + lw and ly < ry + rh and ry < ly + lh
