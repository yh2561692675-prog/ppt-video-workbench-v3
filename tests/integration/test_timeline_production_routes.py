from __future__ import annotations

from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
from workbench.api.timeline_production import TimelineWorkspaceService, create_timeline_router
from workbench.timeline.production import (
    ClipKind,
    ProductionTimeline,
    TimelineCommand,
    TimelineTrack,
)


def test_timeline_routes_initialize_command_and_compile() -> None:
    project_id = uuid4()
    track = TimelineTrack(kind=ClipKind.SLIDE, name="Slides", order=0)
    timeline = ProductionTimeline(project_id=project_id, duration_us=1_000_000, tracks=[track])
    app = FastAPI()
    app.include_router(create_timeline_router(TimelineWorkspaceService()))

    with TestClient(app) as client:
        initialized = client.post(
            f"/api/projects/{project_id}/timeline/initialize", json=timeline.model_dump(mode="json")
        )
        assert initialized.status_code == 201
        assert initialized.json()["data"]["revision"] == 1

        compiled = client.post(f"/api/projects/{project_id}/timeline/compile")
        assert compiled.status_code == 200
        assert compiled.json()["data"]["schema_version"] == "1.0"

        conflict = client.post(
            f"/api/projects/{project_id}/timeline/commands",
            json={
                "expected_revision": 1,
                "kind": "reorder_track",
                "payload": {"track_id": str(track.id), "order": 1},
            },
        )
        assert conflict.status_code == 200
        stale = client.post(
            f"/api/projects/{project_id}/timeline/commands",
            json={
                "expected_revision": 1,
                "kind": "reorder_track",
                "payload": {"track_id": str(track.id), "order": 2},
            },
        )
        assert stale.status_code == 409


def test_timeline_service_reloads_current_and_revision_history(tmp_path) -> None:
    project_id = uuid4()
    track = TimelineTrack(kind=ClipKind.SLIDE, name="Slides", order=0)
    timeline = ProductionTimeline(project_id=project_id, duration_us=1_000_000, tracks=[track])
    first = TimelineWorkspaceService(tmp_path)
    first.initialize(timeline)
    first.apply(
        project_id,
        TimelineCommand(
            expected_revision=1,
            kind="reorder_track",
            payload={"track_id": str(track.id), "order": 1},
        ),
    )
    second = TimelineWorkspaceService(tmp_path)

    assert second.get(project_id).revision == 2
    assert second.revisions(project_id) == [1, 2]


def test_timeline_batch_route_commits_atomically() -> None:
    project_id = uuid4()
    track = TimelineTrack(kind=ClipKind.SLIDE, name="Slides", order=0)
    timeline = ProductionTimeline(project_id=project_id, duration_us=1_000_000, tracks=[track])
    app = FastAPI()
    app.include_router(create_timeline_router(TimelineWorkspaceService()))

    with TestClient(app) as client:
        initialized = client.post(
            f"/api/projects/{project_id}/timeline/initialize", json=timeline.model_dump(mode="json")
        )
        assert initialized.status_code == 201
        response = client.post(
            f"/api/projects/{project_id}/timeline/commands:batch",
            json={
                "expected_revision": 1,
                "commands": [
                    {
                        "expected_revision": 1,
                        "kind": "reorder_track",
                        "payload": {"track_id": str(track.id), "order": 2},
                    },
                    {
                        "expected_revision": 2,
                        "kind": "reorder_track",
                        "payload": {"track_id": str(track.id), "order": 3},
                    },
                ],
            },
        )

    assert response.status_code == 200
    assert response.json()["data"]["revision"] == 3
