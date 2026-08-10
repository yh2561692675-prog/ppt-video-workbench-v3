from __future__ import annotations

from typing import Any

EFFECT_CATALOG_VERSION = "effect-catalog-v2"

EFFECT_CATALOG: tuple[dict[str, Any], ...] = (
    {"name": "ProgressiveReveal", "kind": "progressive_reveal", "internal": False},
    {"name": "ChapterCurtain", "kind": "chapter_curtain", "internal": False},
    {"name": "StatCounter", "kind": "stat_counter", "internal": False},
    {"name": "ChartNarration", "kind": "chart_narration", "internal": False},
    {"name": "CompareMode", "kind": "compare_mode", "internal": False},
    {"name": "FocusSpotlight", "kind": "focus_spotlight", "internal": False},
    {"name": "CardStack", "kind": "card_stack", "internal": False},
    {"name": "GaugeAndRatio", "kind": "gauge_and_ratio", "internal": False},
    {"name": "PathBuilder", "kind": "path_builder", "internal": False},
    {"name": "TagMatrix", "kind": "tag_matrix", "internal": False},
    {"name": "RiskAlert", "kind": "risk_alert", "internal": False},
    {"name": "MapHighlight", "kind": "map_highlight", "internal": False},
    {"name": "SafeSlide", "kind": "safe_slide", "internal": True},
)


def catalog_entries() -> tuple[dict[str, Any], ...]:
    return EFFECT_CATALOG
