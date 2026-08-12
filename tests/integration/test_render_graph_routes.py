from __future__ import annotations

from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from workbench.api.timeline_production import TimelineWorkspaceService, create_timeline_router
from workbench.assets.models import AssetKind, AssetRecord, LicenseRecord, LicenseStatus
from workbench.main import create_app
from workbench.timeline.production import ClipKind, ProductionTimeline, TimelineTrack


def test_render_graph_v2_routes_compile_current_get_preflight_and_ranges() -> None:
    project_id = uuid4()
    timeline = ProductionTimeline(
        project_id=project_id,
        duration_us=1_000_000,
        tracks=[TimelineTrack(kind=ClipKind.SLIDE, name="Slides", order=0)],
    )
    app = FastAPI()
    app.include_router(create_timeline_router(TimelineWorkspaceService()))

    with TestClient(app) as client:
        initialized = client.post(
            f"/api/projects/{project_id}/timeline/initialize",
            json=timeline.model_dump(mode="json"),
        )
        assert initialized.status_code == 201

        compiled = client.post(f"/api/projects/{project_id}/render-graphs:compile")
        assert compiled.status_code == 200
        graph = compiled.json()["data"]
        graph_id = graph["graph_id"]
        assert graph["schema_version"] == "2.0"

        current = client.get(f"/api/projects/{project_id}/render-graphs/current")
        assert current.status_code == 200
        assert current.json()["data"]["graph_id"] == graph_id

        loaded = client.get(f"/api/projects/{project_id}/render-graphs/{graph_id}")
        assert loaded.status_code == 200
        assert loaded.json()["data"]["graph_hash"] == graph["graph_hash"]

        preflight = client.get(f"/api/projects/{project_id}/render-graphs/{graph_id}/preflight")
        assert preflight.status_code == 200
        assert preflight.json()["data"]["allowed"] is True

        ranges = client.get(f"/api/projects/{project_id}/render-graphs/{graph_id}/affected-ranges")
        assert ranges.status_code == 200
        assert ranges.json()["data"] == []

        preview = client.post(
            f"/api/projects/{project_id}/render-graphs/{graph_id}/preview-plan",
            json={
                "start_us": 0,
                "end_us": 500_000,
                "preset": "authoritative",
                "runtime_version": "test-runtime",
            },
        )
        assert preview.status_code == 200
        preview_plan = preview.json()["data"]
        assert preview_plan["graph_id"] == graph_id
        assert preview_plan["graph_hash"] == graph["graph_hash"]
        assert len(preview_plan["cache_key"]) == 64

        invalid_preview = client.post(
            f"/api/projects/{project_id}/render-graphs/{graph_id}/preview-plan",
            json={"start_us": 0, "end_us": 2_000_000},
        )
        assert invalid_preview.status_code == 422

        conflict = client.post(
            f"/api/projects/{project_id}/render-graphs:compile?expected_revision=99"
        )
        assert conflict.status_code == 409
        assert conflict.json()["detail"]["code"] == "timeline_revision_conflict"

        missing = client.get(f"/api/projects/{project_id}/render-graphs/{uuid4()}")
        assert missing.status_code == 404


def test_authoritative_preview_job_route_freezes_graph_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("WORKBENCH_ASYNC_RENDER_ENABLED", "false")
    app = create_app(tmp_path)
    project = app.state.project_service.create("preview job")
    timeline = ProductionTimeline(
        project_id=project.id,
        duration_us=1_000_000,
        tracks=[TimelineTrack(kind=ClipKind.SLIDE, name="Slides", order=0)],
    )

    with TestClient(app) as client:
        client.post(
            f"/api/projects/{project.id}/timeline/initialize",
            json=timeline.model_dump(mode="json"),
        )
        compiled = client.post(f"/api/projects/{project.id}/render-graphs:compile")
        graph = compiled.json()["data"]
        submitted = client.post(
            f"/api/projects/{project.id}/render-graphs/{graph['graph_id']}/preview-jobs",
            json={
                "graph_id": graph["graph_id"],
                "graph_hash": graph["graph_hash"],
                "start_us": 0,
                "end_us": 500_000,
                "runtime_version": "test-runtime",
            },
        )

    assert submitted.status_code == 202
    assert submitted.json()["data"]["job_type"] == "render_preview"
    assert submitted.json()["data"]["payload"]["plan"]["graph_hash"] == graph["graph_hash"]


def test_compile_v2_route_delegates_to_the_authoritative_context_compiler() -> None:
    project_id = uuid4()
    timeline = ProductionTimeline(
        project_id=project_id,
        duration_us=1_000_000,
        tracks=[TimelineTrack(kind=ClipKind.SLIDE, name="Slides", order=0)],
    )
    service = TimelineWorkspaceService()
    calls: list[tuple[UUID, int | None]] = []

    def compile_with_context(request_project_id, expected_revision):
        calls.append((request_project_id, expected_revision))
        return service.compile_v2(
            request_project_id,
            expected_revision=expected_revision,
            assets=[
                AssetRecord(
                    project_id=project_id,
                    kind=AssetKind.IMAGE,
                    content_hash="a" * 64,
                    relative_object_path="page.png",
                    original_name="page.png",
                    mime_type="image/png",
                    size_bytes=1,
                    license=LicenseRecord(status=LicenseStatus.CONFIRMED),
                )
            ],
        )

    app = FastAPI()
    app.include_router(
        create_timeline_router(service, compile_v2_with_context=compile_with_context)
    )

    with TestClient(app) as client:
        initialized = client.post(
            f"/api/projects/{project_id}/timeline/initialize",
            json=timeline.model_dump(mode="json"),
        )
        assert initialized.status_code == 201
        compiled = client.post(
            f"/api/projects/{project_id}/timeline/compile-v2?expected_revision=1"
        )

    assert compiled.status_code == 200
    assert calls == [(project_id, 1)]
