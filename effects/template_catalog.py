from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TemplateSpec:
    name: str
    supported_aspects: tuple[str, ...]
    performance: str
    fallback: str
    mutually_exclusive: tuple[str, ...] = ()


TEMPLATE_CATALOG: tuple[TemplateSpec, ...] = (
    TemplateSpec("StatCounter", ("16:9", "9:16"), "standard", "SafeSlide"),
    TemplateSpec("ChartNarration", ("16:9", "9:16"), "standard", "SafeSlide"),
    TemplateSpec("CompareMode", ("16:9", "9:16"), "standard", "SafeSlide"),
    TemplateSpec("MapHighlight", ("16:9", "9:16"), "standard", "SafeSlide"),
    TemplateSpec("FocusSpotlight", ("16:9", "9:16"), "safe", "SafeSlide"),
    TemplateSpec("ChapterCurtain", ("16:9", "9:16"), "standard", "SafeSlide"),
    TemplateSpec("SafeSlide", ("16:9", "9:16"), "safe", "SafeSlide"),
)


def get_template(name: str) -> TemplateSpec | None:
    return next((item for item in TEMPLATE_CATALOG if item.name == name), None)
