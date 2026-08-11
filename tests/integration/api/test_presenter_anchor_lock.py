from pathlib import Path
from uuid import UUID

from fastapi.testclient import TestClient
from workbench.domain.models import ProjectManifest
from workbench.domain.presenter import PresenterTimelineV1, SlideAnchor
from workbench.main import create_app
from workbench.media.presenter_probe import PresenterMediaInfo


def _probe(path: Path) -> PresenterMediaInfo:
    return PresenterMediaInfo(
        path=str(path),
        sha256="a" * 64,
        duration_ms=3_000,
        container="mp4",
        video_codec="h264",
        audio_codec="aac",
        width=1920,
        height=1080,
        fps=30,
        sample_rate=48_000,
        channels=2,
    )


def _project_with_timeline(client: TestClient, app) -> dict[str, object]:
    project = client.post("/api/projects", json={"name": "presenter-lock"}).json()["data"]
    uploaded = client.post(
        f"/api/projects/{project['id']}/presenter-source",
        files={"file": ("presenter.mp4", b"video", "video/mp4")},
    ).json()["data"]
    manifest = ProjectManifest.model_validate(uploaded)
    timeline = PresenterTimelineV1(
        source_id=manifest.presenter_source.id,
        source_version=manifest.presenter_source.sha256,
        duration_ms=3_000,
        anchors=[
            SlideAnchor(
                page_id=UUID(int=1),
                start_ms=0,
                end_ms=1_500,
                confidence=0.9,
                status="auto",
                source_revision="a" * 64,
            ),
            SlideAnchor(
                page_id=UUID(int=2),
                start_ms=1_500,
                end_ms=3_000,
                confidence=0.9,
                status="auto",
                source_revision="a" * 64,
            ),
        ],
    )
    payload = manifest.model_dump(mode="python")
    payload["presenter_timeline"] = timeline
    app.state.project_service.save(ProjectManifest.model_validate(payload))
    return uploaded


def test_anchor_patch_locks_revision_and_survives_reload(tmp_path: Path) -> None:
    app = create_app(tmp_path, presenter_probe=_probe)
    with TestClient(app) as client:
        project = _project_with_timeline(client, app)
        response = client.patch(
            f"/api/projects/{project['id']}/presenter-timeline/anchors/{UUID(int=1)}",
            json={"expected_revision": 1, "start_ms": 0, "end_ms": 1_400},
        )
        assert response.status_code == 200
        timeline = response.json()["data"]["presenter_timeline"]
        assert timeline["revision"] == 2
        assert timeline["anchors"][0]["manual_lock"] is True
        assert timeline["anchors"][0]["source_revision"] == "a" * 64

        reloaded = client.get(f"/api/projects/{project['id']}").json()["data"]
        assert reloaded["presenter_timeline"] == timeline


def test_anchor_patch_returns_current_revision_on_conflict(tmp_path: Path) -> None:
    app = create_app(tmp_path, presenter_probe=_probe)
    with TestClient(app) as client:
        project = _project_with_timeline(client, app)
        response = client.patch(
            f"/api/projects/{project['id']}/presenter-timeline/anchors/{UUID(int=1)}",
            json={"expected_revision": 2, "start_ms": 0, "end_ms": 1_400},
        )
        assert response.status_code == 409
        assert response.json()["error"]["current_revision"] == 1


def test_anchor_patch_rejects_overlap(tmp_path: Path) -> None:
    app = create_app(tmp_path, presenter_probe=_probe)
    with TestClient(app) as client:
        project = _project_with_timeline(client, app)
        response = client.patch(
            f"/api/projects/{project['id']}/presenter-timeline/anchors/{UUID(int=1)}",
            json={"expected_revision": 1, "start_ms": 0, "end_ms": 1_600},
        )
        assert response.status_code == 422
