from __future__ import annotations

import pytest

from effects.backgrounds import choose_background


@pytest.mark.parametrize(
    ("semantic", "preset"),
    [
        ("risk", "risk_red"),
        ("conclusion", "warm_gold"),
        ("fact", "tech_blue"),
        ("academic_light", "paper_grid"),
        ("regional", "regional_teal"),
    ],
)
def test_background_semantics(semantic: str, preset: str) -> None:
    assert choose_background(semantic, "education") == preset


def test_unknown_semantics_use_safe_technology_background() -> None:
    assert choose_background("unknown", "education") == "tech_blue"
