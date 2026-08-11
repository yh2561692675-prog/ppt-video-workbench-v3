from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import pytest
from workbench.quality.engine import QualityProcessResult, QualityService
from workbench.quality.jobs import (
    QualityJobRequest,
    QualityJobService,
    QualityJobStatus,
    QualityRetryLimitError,
)


def _runner(command, _cwd: Path) -> QualityProcessResult:
    if command[0] == "ffprobe":
        return QualityProcessResult(
            returncode=0,
            stdout=json.dumps(
                {
                    "streams": [
                        {
                            "codec_type": "video",
                            "codec_name": "h264",
                            "width": 1920,
                            "height": 1080,
                            "r_frame_rate": "30/1",
                        },
                        {"codec_type": "audio", "codec_name": "aac"},
                    ],
                    "format": {"duration": "2.000"},
                }
            ),
        )
    return QualityProcessResult(returncode=0)


def test_quality_job_service_rejects_path_escape(tmp_path: Path) -> None:
    service = QualityJobService(tmp_path, analyzer=QualityService(runner=_runner))
    record = service.submit(
        uuid4(),
        QualityJobRequest(video_path="../outside.mp4", expected_duration_ms=2_000),
    )

    assert record.status is QualityJobStatus.FAILED
    assert record.error_code == "quality_path_outside_project"


def test_quality_job_service_writes_report_and_supports_retry(tmp_path: Path) -> None:
    project_id = uuid4()
    project_root = tmp_path / str(project_id)
    project_root.mkdir()
    (project_root / "video.mp4").write_bytes(b"valid-media")
    service = QualityJobService(tmp_path, analyzer=QualityService(runner=_runner))

    first = service.submit(
        project_id,
        QualityJobRequest(video_path="video.mp4", expected_duration_ms=2_000),
    )
    retried = service.retry(project_id, first.job_id)

    assert first.status is QualityJobStatus.SUCCEEDED
    assert retried.status is QualityJobStatus.SUCCEEDED
    assert retried.job_id != first.job_id
    assert retried.retry_of_job_id == first.job_id
    assert retried.retry_count == 1
    assert first.report is not None
    assert (tmp_path / str(project_id) / (first.report.report_path or "")).is_file()

    with pytest.raises(QualityRetryLimitError):
        service.retry(project_id, first.job_id)


def test_quality_job_service_redacts_unexpected_failure_details(tmp_path: Path) -> None:
    project_id = uuid4()
    project_root = tmp_path / str(project_id)
    project_root.mkdir()
    (project_root / "video.mp4").write_bytes(b"valid-media")

    def raising_runner(_command, cwd: Path) -> QualityProcessResult:
        raise RuntimeError(f"failed while reading {cwd / 'private.log'}")

    service = QualityJobService(
        tmp_path,
        analyzer=QualityService(runner=raising_runner),
    )
    record = service.submit(
        project_id,
        QualityJobRequest(video_path="video.mp4", expected_duration_ms=2_000),
    )

    assert record.status is QualityJobStatus.FAILED
    assert record.error_code == "quality_analysis_failed"
    assert record.error == "质量分析未完成，请检查运行时日志后重试"
    assert str(tmp_path) not in (record.error or "")
