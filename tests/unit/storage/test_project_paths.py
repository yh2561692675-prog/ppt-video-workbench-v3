from pathlib import Path
from types import SimpleNamespace

import pytest
from workbench.services.project_service import ProjectService
from workbench.storage import project_paths
from workbench.storage.project_paths import ProjectStorageError, ProjectStorageRoots


def test_new_project_maps_video_and_output_folders_to_configured_roots(tmp_path: Path) -> None:
    service = ProjectService(
        tmp_path / "workspace",
        storage_roots=ProjectStorageRoots(tmp_path / "cache", tmp_path / "output"),
    )

    project = service.create("分流测试")
    project_root = service.workspace_root / project.project_dir

    assert (project_root / "07_视频工程").resolve() == (
        tmp_path / "cache" / project.project_dir
    ).resolve()
    assert (project_root / "08_输出").resolve() == (
        tmp_path / "output" / project.project_dir
    ).resolve()


def test_project_creation_fails_when_configured_cache_root_is_not_a_directory(
    tmp_path: Path,
) -> None:
    blocked_root = tmp_path / "blocked-file"
    blocked_root.write_text("not a directory", encoding="utf-8")
    with pytest.raises(ProjectStorageError, match="缓存目录"):
        ProjectService(
            tmp_path / "workspace",
            storage_roots=ProjectStorageRoots(blocked_root, tmp_path / "output"),
        )


def test_junction_creation_error_keeps_windows_diagnostic_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    link = tmp_path / "07_视频工程"
    target = tmp_path / "cache"

    monkeypatch.setattr(project_paths.os, "name", "nt")
    monkeypatch.setattr(
        project_paths.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=1,
            stdout="Cannot create a file when that file already exists.\n",
            stderr="",
        ),
    )

    with pytest.raises(ProjectStorageError) as error:
        project_paths._link_directory(link, target)

    assert "退出码 1" in str(error.value)
    assert "Cannot create a file" in str(error.value)


def test_windows_junction_command_is_passed_to_cmd_as_one_raw_command_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    link = tmp_path / "07_视频工程"
    target = tmp_path / "cache"
    commands: list[str] = []

    monkeypatch.setattr(project_paths.os, "name", "nt")
    monkeypatch.setattr(
        project_paths.subprocess,
        "run",
        lambda command, **kwargs: (
            commands.append(command) or SimpleNamespace(returncode=0, stdout="", stderr="")
        ),
    )

    project_paths._link_directory(link, target)

    assert commands == [f'cmd.exe /d /c mklink /J "{link}" "{target}"']
