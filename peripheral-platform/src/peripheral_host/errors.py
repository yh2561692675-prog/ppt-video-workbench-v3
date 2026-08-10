from __future__ import annotations


class PeripheralError(Exception):
    """Base class for stable peripheral-host failures."""


class WorkspacePathError(PeripheralError, ValueError):
    def __init__(self, relative_path: object) -> None:
        super().__init__(f"workspace path rejected: {relative_path!r}")
        self.relative_path = relative_path


class ArtifactIntegrityError(PeripheralError, ValueError):
    """An input artifact does not match its frozen reference."""


class ArtifactPublishError(PeripheralError, ValueError):
    """A staged output cannot be published as an immutable artifact."""
