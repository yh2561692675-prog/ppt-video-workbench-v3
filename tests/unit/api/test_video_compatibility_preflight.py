from __future__ import annotations

from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
from workbench.api.video import create_video_router
from workbench.video.models import PreflightIssue, VideoPreflight


class LegacyServiceMustNotRun:
    def preflight(self, project_id, reduced_motion=None):
        raise AssertionError("legacy preflight must not run for a compatibility source")


def test_video_preflight_uses_v2_or_legacy_compatibility_projection() -> None:
    project_id = uuid4()
    app = FastAPI()
    app.include_router(
        create_video_router(
            LegacyServiceMustNotRun(),
            compatibility_preflight=lambda _: VideoPreflight(
                allowed=False,
                issues=[
                    PreflightIssue(
                        code="ASSET_MISSING",
                        message="missing",
                        action="replace",
                    )
                ],
            ),
        )
    )

    with TestClient(app) as client:
        response = client.post(f"/api/projects/{project_id}/video/preflight")

    assert response.status_code == 200
    assert response.json()["data"]["allowed"] is False
    assert response.json()["data"]["issues"][0]["code"] == "ASSET_MISSING"
