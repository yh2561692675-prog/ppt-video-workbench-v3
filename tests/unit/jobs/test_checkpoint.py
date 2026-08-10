from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from workbench.domain.enums import JobType
from workbench.jobs.checkpoint import CheckpointStore, JobContext


def test_checkpoint_is_atomic_sanitized_and_hash_verified(tmp_path: Path) -> None:
    project_dir = tmp_path / "项目"
    project_dir.mkdir()
    artifact = project_dir / "02_页面预览" / "page-1.png"
    artifact.parent.mkdir()
    artifact.write_bytes(b"stable-page")
    context = JobContext(uuid4(), project_dir, JobType.PARSE_MATERIALS)

    checkpoint = context.checkpoint(
        0.3,
        {
            "stage": "ocr",
            "api_token": "must-not-be-written",
            "completed_pages": [1],
        },
        artifacts=(artifact,),
    )

    target = project_dir / "09_日志" / "检查点"
    files = list(target.glob("*.json"))
    assert len(files) == 1
    assert checkpoint.progress == 0.3
    assert checkpoint.artifacts[0].sha256
    assert "must-not-be-written" not in files[0].read_text(encoding="utf-8")
    assert CheckpointStore(project_dir).restore(checkpoint.job_id) == checkpoint

    artifact.write_bytes(b"changed-page")
    assert CheckpointStore(project_dir).restore(checkpoint.job_id) is None


def test_pause_and_cancel_only_remove_declared_temporary_files(tmp_path: Path) -> None:
    project_dir = tmp_path / "项目"
    project_dir.mkdir()
    temporary = project_dir / "07_视频工程" / "render.tmp"
    temporary.parent.mkdir()
    temporary.write_bytes(b"temporary")
    protected = project_dir / "08_输出" / "final.mp4"
    protected.parent.mkdir()
    protected.write_bytes(b"final")
    context = JobContext(uuid4(), project_dir, JobType.RENDER_PAGE)
    context.checkpoint(
        0.7,
        {"temporary_paths": ["07_视频工程/render.tmp"]},
    )

    context.request_pause()
    assert context.should_pause is True
    assert temporary.exists()
    context.request_cancel()
    assert context.should_cancel is True
    assert not temporary.exists()
    assert protected.exists()
