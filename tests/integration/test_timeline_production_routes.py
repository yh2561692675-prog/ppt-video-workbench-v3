from __future__ import annotations

from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
from workbench.api.timeline_production import TimelineWorkspaceService, create_timeline_router
from workbench.timeline.production import (
    ClipKind,
    ProductionTimeline,
    TimelineClip,
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

        uncompiled = client.get(f"/api/projects/{project_id}/render-graph-v2")
        assert uncompiled.status_code == 200
        assert uncompiled.json()["data"] is None

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


def test_timeline_optional_resources_are_empty_before_initialization() -> None:
    project_id = uuid4()
    app = FastAPI()
    app.include_router(create_timeline_router(TimelineWorkspaceService()))

    with TestClient(app) as client:
        timeline = client.get(f"/api/projects/{project_id}/timeline")
        revisions = client.get(f"/api/projects/{project_id}/timeline/revisions")

    assert timeline.status_code == 200
    assert timeline.json()["data"] is None
    assert revisions.status_code == 200
    assert revisions.json()["data"] == []


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


def test_timeline_service_reloads_before_a_direct_v2_compile(tmp_path) -> None:
    project_id = uuid4()
    timeline = ProductionTimeline(
        project_id=project_id,
        duration_us=1_000_000,
        tracks=[TimelineTrack(kind=ClipKind.SLIDE, name="Slides", order=0)],
    )
    TimelineWorkspaceService(tmp_path).initialize(timeline)

    graph = TimelineWorkspaceService(tmp_path).compile_v2(project_id)

    assert graph.project_id == project_id
    assert graph.timeline_revision == 1


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


def test_timeline_command_returns_validation_error_instead_of_server_error() -> None:
    project_id = uuid4()
    track = TimelineTrack(kind=ClipKind.SLIDE, name="Slides", order=0)
    track.clips = [
        TimelineClip(
            track_id=track.id,
            kind=ClipKind.SLIDE,
            start_us=0,
            duration_us=500_000,
            source_ref="page-1.png",
        ),
        TimelineClip(
            track_id=track.id,
            kind=ClipKind.SLIDE,
            start_us=500_000,
            duration_us=500_000,
            source_ref="page-2.png",
        ),
    ]
    timeline = ProductionTimeline(project_id=project_id, duration_us=1_000_000, tracks=[track])
    app = FastAPI()
    app.include_router(create_timeline_router(TimelineWorkspaceService()))

    with TestClient(app) as client:
        initialized = client.post(
            f"/api/projects/{project_id}/timeline/initialize", json=timeline.model_dump(mode="json")
        )
        assert initialized.status_code == 201
        invalid = client.post(
            f"/api/projects/{project_id}/timeline/commands",
            json={
                "expected_revision": 1,
                "kind": "move_clip",
                "payload": {"clip_id": str(track.clips[0].id), "start_us": 1},
            },
        )

    assert invalid.status_code == 422
    assert invalid.json()["detail"]["code"] == "invalid_timeline"
