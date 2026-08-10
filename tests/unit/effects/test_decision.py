from __future__ import annotations

import json
from pathlib import Path

from effects.decision import recommend_effect

FIXTURE_PATH = Path(__file__).parents[2] / "fixtures" / "effects" / "decision-cases.json"


def test_template_recommendations_cover_reference_semantics() -> None:
    cases = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    decisions = [
        recommend_effect(case["page"], case.get("cues", []), case.get("policy", {}))
        for case in cases
    ]

    assert [decision.template for decision in decisions] == [
        "StatCounter",
        "ChartNarration",
        "CompareMode",
        "MapHighlight",
        "FocusSpotlight",
    ]
    assert all(decision.confidence >= 0.8 for decision in decisions)
    assert all(decision.reasons for decision in decisions)


def test_dense_text_uses_restrained_strength() -> None:
    decision = recommend_effect({"text_density": 0.9, "text": "很多正文"}, [], {})

    assert decision.template == "FocusSpotlight"
    assert decision.strength == "restrained"


def test_manual_template_lock_wins_over_reanalysis() -> None:
    decision = recommend_effect(
        {"manual_template": "ChartNarration", "manual_lock": True, "modules": ["risk"]},
        [],
        {},
    )

    assert decision.template == "ChartNarration"
    assert decision.manual_lock is True
    assert "manual_lock" in decision.reasons
