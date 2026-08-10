from __future__ import annotations

from typing import Literal


BackgroundPreset = Literal["tech_blue", "risk_red", "warm_gold", "paper_grid", "regional_teal"]


def choose_background(page_semantics: str, project_style: str) -> BackgroundPreset:
    del project_style
    return {
        "risk": "risk_red",
        "conclusion": "warm_gold",
        "fact": "tech_blue",
        "academic_light": "paper_grid",
        "regional": "regional_teal",
    }.get(page_semantics, "tech_blue")
