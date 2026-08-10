from __future__ import annotations

from typing import Final

SCHEMA_VERSION: Final = "1.0"
SUPPORTED_SCHEMA_MAJOR: Final = 1


class UnsupportedSchemaVersion(ValueError):
    def __init__(self, schema_version: object) -> None:
        super().__init__(f"Unsupported schema major version: {schema_version!r}")
        self.schema_version = schema_version


def require_supported_major(schema_version: object) -> None:
    if not isinstance(schema_version, str):
        return
    major, separator, _ = schema_version.partition(".")
    if not separator or not major.isdigit():
        return
    if int(major) != SUPPORTED_SCHEMA_MAJOR:
        raise UnsupportedSchemaVersion(schema_version)
