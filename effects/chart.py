from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ChartStep:
    kind: str
    payload: tuple[tuple[str, object], ...] = ()


def build_chart_sequence(
    series: list[dict[str, object]],
    cue_points: list[dict[str, object]],
    annotation: str,
) -> tuple[ChartStep, ...]:
    numeric_series = [item for item in series if _is_number(item.get("value"))]
    if not numeric_series:
        return (ChartStep("static_fallback", (("annotation", annotation),)),)

    key_points = cue_points or [{"index": 0, "text": ""}]
    return (
        ChartStep("baseline"),
        ChartStep("series", (("count", len(numeric_series)),)),
        ChartStep("key_point", (("count", len(key_points)),)),
        ChartStep("annotation", (("text", annotation),)),
        ChartStep("conclusion", (("text", annotation),)),
    )


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)
