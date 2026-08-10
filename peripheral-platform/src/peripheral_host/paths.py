from __future__ import annotations

from pathlib import Path, PureWindowsPath

from peripheral_host.errors import WorkspacePathError

WINDOWS_DEVICE_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}


def _validated_windows_parts(relative: str) -> tuple[str, ...]:
    pure = PureWindowsPath(relative)
    if (
        not pure.parts
        or pure.is_absolute()
        or bool(pure.drive)
        or bool(pure.root)
        or ".." in pure.parts
    ):
        raise WorkspacePathError(relative)

    for part in pure.parts:
        normalized_part = part.rstrip(" .")
        device_stem = normalized_part.upper().split(".")[0]
        if (
            not normalized_part
            or normalized_part != part
            or ":" in part
            or device_stem in WINDOWS_DEVICE_NAMES
        ):
            raise WorkspacePathError(relative)
    return pure.parts


def lexical_workspace_path(root: Path, relative: str) -> Path:
    return root.resolve().joinpath(*_validated_windows_parts(relative))


def resolve_workspace_path(root: Path, relative: str) -> Path:
    root_resolved = root.resolve()
    normalized = lexical_workspace_path(root_resolved, relative).resolve(strict=False)
    if normalized == root_resolved or not normalized.is_relative_to(root_resolved):
        raise WorkspacePathError(relative)
    return normalized
