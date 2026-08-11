from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
from workbench.api.quality import create_quality_router
from workbench.quality.engine import QualityProcessResult, QualityService
from workbench.quality.jobs import QualityJobService


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


def test_quality_routes_submit_latest_and_block_path_escape(tmp_path: Path) -> None:
    project_id = uuid4()
    project_root = tmp_path / str(project_id)
    project_root.mkdir()
    (project_root / "video.mp4").write_bytes(b"valid-media")
    app = FastAPI()
    app.include_router(
        create_quality_router(QualityJobService(tmp_path, analyzer=QualityService(runner=_runner)))
    )

    with TestClient(app) as client:
        response = client.post(
            f"/api/projects/{project_id}/quality/jobs",
            json={"video_path": "video.mp4", "expected_duration_ms": 2_000},
        )
        assert response.status_code == 201
        body = response.json()["data"]
        assert body["status"] == "succeeded"
        job_id = body["job_id"]
        assert body["report"]["report_path"].startswith("09_日志/")
        assert str(tmp_path) not in body["report"]["report_path"]

        latest = client.get(f"/api/projects/{project_id}/quality/latest")
        assert latest.status_code == 200
        assert latest.json()["data"]["job_id"] == job_id

        reloaded = QualityJobService(tmp_path, analyzer=QualityService(runner=_runner))
        assert str(reloaded.latest(project_id).job_id) == job_id
        retried = reloaded.retry(project_id, UUID(job_id))
        assert retried.status == "succeeded"

        blocked = client.post(
            f"/api/projects/{project_id}/quality/jobs",
            json={
                "video_path": "video.mp4",
                "expected_duration_ms": 2_000,
                "expected_width": 1280,
            },
        )
        issue_id = blocked.json()["data"]["report"]["issues"][0]["issue_id"]
        confirmed = client.post(
            f"/api/projects/{project_id}/quality/jobs/{blocked.json()['data']['job_id']}"
            f"/issues/{issue_id}/actions",
            json={"action": "confirm", "note": "已人工复核"},
        )
        assert confirmed.status_code == 201
        assert issue_id in confirmed.json()["data"]["confirmed_issue_ids"]
        action = client.post(
            f"/api/projects/{project_id}/quality/jobs/{blocked.json()['data']['job_id']}"
            f"/issues/{issue_id}/actions",
            json={"action": "retry"},
        )
        assert action.status_code == 201
        limited = client.post(
            f"/api/projects/{project_id}/quality/jobs/{blocked.json()['data']['job_id']}/retry"
        )
        assert limited.status_code == 409
        assert limited.json()["detail"]["code"] == "quality_retry_limit_reached"

        escaped = client.post(
            f"/api/projects/{project_id}/quality/jobs",
            json={"video_path": "../outside.mp4", "expected_duration_ms": 2_000},
        )
        assert escaped.status_code == 201
        assert escaped.json()["data"]["error_code"] == "quality_path_outside_project"
