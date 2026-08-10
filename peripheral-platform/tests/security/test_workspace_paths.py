from __future__ import annotations

from pathlib import Path

import pytest
from peripheral_host.errors import WorkspacePathError
from peripheral_host.paths import resolve_workspace_path


@pytest.mark.parametrize(
    "candidate",
    [
        "../outside.txt",
        "C:/Windows/System32/cmd.exe",
        r"\\server\share\file.mp4",
        "projects/x/../../outside.txt",
        "CON",
        "reports/NUL.txt",
        "projects/demo/file.txt:stream",
        "projects/demo/trailing. ",
        "",
    ],
)
def test_workspace_path_rejects_escape(tmp_path: Path, candidate: str):
    with pytest.raises(WorkspacePathError):
        resolve_workspace_path(tmp_path, candidate)


def test_workspace_path_normalizes_windows_separators(tmp_path: Path):
    resolved = resolve_workspace_path(tmp_path, r"projects\demo\input.pptx")

    assert resolved == tmp_path.resolve() / "projects" / "demo" / "input.pptx"


def test_workspace_path_rejects_symlink_parent_escape(tmp_path: Path):
    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    outside.mkdir()
    try:
        (tmp_path / "linked").symlink_to(outside, target_is_directory=True)
    except OSError as error:
        if error.winerror == 1314:
            pytest.skip("symbolic links require Windows Developer Mode or elevated permission")
        raise

    with pytest.raises(WorkspacePathError):
        resolve_workspace_path(tmp_path, "linked/file.txt")
