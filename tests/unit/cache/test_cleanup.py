from __future__ import annotations

from pathlib import Path

import pytest
from workbench.cache.cleanup import CleanupError, CleanupService, estimate_cleanup
from workbench.domain.models import ProjectManifest
from workbench.services.project_service import ProjectService


def _project(tmp_path: Path) -> ProjectManifest:
    return ProjectService(tmp_path).create("清理测试")


def test_estimate_only_selects_rebuildable_cache_and_protects_project_data(
    tmp_path: Path,
) -> None:
    project = _project(tmp_path)
    root = tmp_path / project.project_dir
    files = {
        "01_源文件/source.pptx": b"source",
        "02_页面预览/page-1.png": b"preview",
        "05_音频/page-1.wav": b"recording",
        "05_音频/缓存/page-1.tmp": b"audio-cache",
        "06_字幕/字幕.srt": b"subtitle",
        "07_视频工程/segments/page-1.mp4": b"segment",
        "08_输出/最终视频.mp4": b"final",
        "09_日志/预检/old.json": b"report",
        "09_日志/检查点/11111111-1111-1111-1111-111111111111-000001.json": b"checkpoint",
    }
    for relative, content in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    plan = estimate_cleanup(project, root)

    assert set(plan.relative_paths) == {
        "02_页面预览/page-1.png",
        "05_音频/缓存/page-1.tmp",
        "06_字幕/字幕.srt",
        "07_视频工程/segments/page-1.mp4",
        "09_日志/预检/old.json",
    }
    assert plan.bytes_reclaimable == sum(len(files[relative]) for relative in plan.relative_paths)
    assert "project.json" in plan.protected_paths
    assert "01_源文件/source.pptx" in plan.protected_paths
    assert "08_输出/最终视频.mp4" in plan.protected_paths
    assert plan.affected_nodes
    assert plan.confirmation_token


def test_cleanup_interruption_rolls_back_files_and_manifest(
    tmp_path: Path,
) -> None:
    projects = ProjectService(tmp_path)
    project = projects.create("中断清理")
    root = tmp_path / project.project_dir
    for name in ("page-1.png", "page-2.png"):
        path = root / "02_页面预览" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(name.encode())
    calls = 0

    def move(source: Path, destination: Path) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("simulated interruption")
        source.rename(destination)

    service = CleanupService(projects, move=move)
    plan = service.estimate(project.id)
    before_manifest = (root / "project.json").read_bytes()

    with pytest.raises(CleanupError):
        service.execute(project.id, plan.id, plan.confirmation_token)

    assert (root / "project.json").read_bytes() == before_manifest
    assert (root / "02_页面预览/page-1.png").is_file()
    assert (root / "02_页面预览/page-2.png").is_file()
