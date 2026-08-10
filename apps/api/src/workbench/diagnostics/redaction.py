from __future__ import annotations

import re
from pathlib import Path
from typing import Any

_SENSITIVE_KEY = re.compile(
    r"(?i)(?:api[_-]?key|token|secret|authorization|cookie|password|credential)"
)
_BEARER = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+")
_JWT = re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b")
_LABELLED_SECRET = re.compile(
    r"(?i)\b(api[_-]?key|token|secret|authorization|cookie|password|credential)"
    r"(\s*[:=]\s*)(?!Bearer\s+\*{3}(?:\s|$))([^\s,;]+)"
)
_QUERY_SECRET = re.compile(r"(?i)([?&](?:api[_-]?key|token|key|secret|password)=)[^&\s]+")
_WINDOWS_PROFILE = re.compile(r"(?i)\b[A-Z]:\\Users\\[^\\/\s]+")


def redact_value(
    value: Any,
    *,
    workspace_root: Path | None = None,
    username: str | None = None,
) -> Any:
    if isinstance(value, dict):
        return {
            str(key): (
                "***"
                if _SENSITIVE_KEY.search(str(key))
                else redact_value(
                    item,
                    workspace_root=workspace_root,
                    username=username,
                )
            )
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [
            redact_value(item, workspace_root=workspace_root, username=username) for item in value
        ]
    if isinstance(value, str):
        return redact_text(value, workspace_root=workspace_root, username=username)
    return value


def redact_text(
    text: str,
    *,
    workspace_root: Path | None = None,
    username: str | None = None,
) -> str:
    result = text
    if workspace_root is not None:
        variants = {str(workspace_root), workspace_root.as_posix()}
        for variant in sorted(variants, key=len, reverse=True):
            if variant:
                result = re.sub(re.escape(variant), "%WORKBENCH_WORKSPACE%", result, flags=re.I)
    result = _WINDOWS_PROFILE.sub("%USERPROFILE%", result)
    result = _JWT.sub("***", result)
    result = _BEARER.sub("Bearer ***", result)
    result = _QUERY_SECRET.sub(r"\1***", result)
    result = _LABELLED_SECRET.sub(r"\1\2***", result)
    if username:
        result = re.sub(re.escape(username), "%USERNAME%", result, flags=re.I)
    return result
