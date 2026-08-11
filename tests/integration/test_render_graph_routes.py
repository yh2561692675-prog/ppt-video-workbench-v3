from __future__ import annotations

from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
from workbench.api.timeline_production import TimelineWorkspaceService, create_timeline_router
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
