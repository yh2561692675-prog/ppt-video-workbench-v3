from __future__ import annotations

import re
import unicodedata

PUNCTUATION = re.compile(r"[^0-9a-zA-Z\u4e00-\u9fff%]+")


def normalize_presenter_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text).lower()
    return " ".join(PUNCTUATION.sub(" ", normalized).split())


def text_features(text: str) -> set[str]:
    normalized = normalize_presenter_text(text).replace(" ", "")
    if len(normalized) < 2:
        return {normalized} if normalized else set()
    return {normalized[index : index + 2] for index in range(len(normalized) - 1)}
