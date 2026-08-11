"""Privacy checks for the small P2 diagnostic summary."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

_SECRET_MARKER = re.compile(
    r"(?i)(api[_-]?key|token|secret|authorization|cookie|password|credential)"
)
_EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
_ABSOLUTE_PATH = re.compile(r"(?:^[A-Za-z]:[\\/]|^[/\\]|\\\\[^\\/]+[\\/])")
_RAW_BODY_KEY = re.compile(r"(?i)^(prompt|text|content|body|messages|transcript|raw_input)$")


def _is_secret_key(name: str) -> bool:
    normalized = name.lower().replace("-", "_")
    if normalized.endswith(("_schema_id", "_ref", "_status")):
        return False
    return bool(_SECRET_MARKER.search(normalized))


@dataclass(frozen=True)
class PrivacyFinding:
    code: str
    field: str


def scan_p2_summary(value: Any, *, max_findings: int = 100) -> list[PrivacyFinding]:
    """Return codes and field paths only; never echo the offending value."""

    findings: list[PrivacyFinding] = []

    def add(code: str, field: str) -> None:
        if len(findings) < max_findings:
            findings.append(PrivacyFinding(code, field))

    def visit(item: Any, field: str) -> None:
        if len(findings) >= max_findings:
            return
        if isinstance(item, Mapping):
            for key, nested in item.items():
                name = str(key)
                child = f"{field}.{name}" if field else name
                if _is_secret_key(name):
                    add("secret_key", child)
                if _RAW_BODY_KEY.fullmatch(name):
                    add("raw_body", child)
                visit(nested, child)
            return
        if isinstance(item, Sequence) and not isinstance(item, (str, bytes, bytearray)):
            for index, nested in enumerate(item):
                visit(nested, f"{field}[{index}]")
            return
        if not isinstance(item, str):
            return
        if _EMAIL.search(item):
            add("user_email", field)
        if _ABSOLUTE_PATH.search(item):
            add("absolute_path", field)
        if re.search(
            r"(?i)(?:api[_-]?key|token|secret|authorization|cookie|password)"
            r"\s*[:=]\s*\S+|\bBearer\s+\S+",
            item,
        ):
            add("secret_value", field)

    visit(value, "")
    return findings
