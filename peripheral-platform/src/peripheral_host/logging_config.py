from __future__ import annotations

import hashlib
import json
import logging
import re
from collections.abc import Mapping, Sequence
from typing import Any

SENSITIVE_KEYS = frozenset(
    {
        "authorization",
        "api_key",
        "token",
        "access_token",
        "refresh_token",
        "cookie",
        "set-cookie",
        "secret",
    }
)

_BEARER_PATTERN = re.compile(r"(?i)Bearer\s+[A-Za-z0-9._~+/=-]+")
_WINDOWS_USER_DIRECTORY = re.compile(r"(?i)[A-Z]:[\\/]+Users[\\/]+[^\\/\s]+")


def redact(value: object) -> object:
    """Return a logging-safe copy of a nested value."""
    return _redact(value, parent_key=None)


def _redact(value: object, *, parent_key: str | None) -> object:
    if isinstance(value, Mapping):
        sanitized: dict[object, object] = {}
        for key, child in value.items():
            normalized = str(key).lower()
            if normalized in SENSITIVE_KEYS:
                sanitized[key] = "***"
            elif parent_key == "parameters" and normalized == "text" and isinstance(
                child, str
            ):
                sanitized[key] = {
                    "character_count": len(child),
                    "sha256_prefix": hashlib.sha256(child.encode("utf-8")).hexdigest()[:12],
                }
            else:
                sanitized[key] = _redact(child, parent_key=normalized)
        return sanitized
    if isinstance(value, str):
        if _BEARER_PATTERN.fullmatch(value):
            return "***"
        without_bearer = _BEARER_PATTERN.sub("Bearer ***", value)
        return _WINDOWS_USER_DIRECTORY.sub("%USERPROFILE%", without_bearer)
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        return [_redact(item, parent_key=parent_key) for item in value]
    return value


class RedactingJsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "level": record.levelname.lower(),
            "logger": record.name,
            "message": record.getMessage(),
        }
        fields = getattr(record, "fields", None)
        if fields is not None:
            payload["fields"] = fields
        if record.exc_info and record.exc_info[0] is not None:
            payload["exception_type"] = record.exc_info[0].__name__
        return json.dumps(redact(payload), ensure_ascii=False, separators=(",", ":"))


def configure_logging(level: int = logging.INFO) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(RedactingJsonFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)
