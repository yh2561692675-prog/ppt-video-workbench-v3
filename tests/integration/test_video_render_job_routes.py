from __future__ import annotations

from fastapi.testclient import TestClient
from workbench.domain.enums import JobType
from workbench.jobs.repository import JobSpec
from workbench.main import create_app
from workbench.video.render_job import RenderJobSubmission


def test_render_job_preflight_block_returns_conflict(tmp_path) -> None:
    app = create_app(tmp_path)
    project = app.state.project_service.create("async render")
    with TestClient(app) as client:
        response = client.post(f"/api/projects/{project.id}/video/render-jobs")
    assert response.status_code == 409


def test_render_job_get_supports_weak_etag(tmp_path) -> None:
    app = create_app(tmp_path)
    project = app.state.project_service.create("async render")
    record = app.state.project_service.jobs.enqueue_or_get(
        JobSpec(project_id=project.id, job_type=JobType.EXPORT_PACKAGE, cache_key="test-etag")
    ).record
    with TestClient(app) as client:
        first = client.get(f"/api/projects/{project.id}/video/render-jobs/{record.id}")
        assert first.status_code == 200
        second = client.get(
            f"/api/projects/{project.id}/video/render-jobs/{record.id}",
            headers={"If-None-Match": first.headers["etag"]},
        )
    assert second.status_code == 304


def test_reused_render_job_returns_200_and_current_returns_latest_terminal(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("WORKBENCH_ASYNC_RENDER_ENABLED", "false")
    app = create_app(tmp_path)
    project = app.state.project_service.create("async render")
    repository = app.state.project_service.jobs
    record = repository.enqueue_or_get(
        JobSpec(project_id=project.id, job_type=JobType.EXPORT_PACKAGE, cache_key="terminal")
    ).record
    repository.mark_running(record.id)
    terminal = repository.succeed(record.id, {"package_relative_path": "08_输出/package"})
    monkeypatch.setattr(
        app.state.render_job_service,
        "submit",
        lambda project_id: RenderJobSubmission(terminal, False),
    )

    with TestClient(app) as client:
        reused = client.post(f"/api/projects/{project.id}/video/render-jobs")
        current = client.get(f"/api/projects/{project.id}/video/render-jobs/current")

    assert reused.status_code == 200
    assert reused.json()["data"]["created"] is False
    assert current.status_code == 200
    assert current.json()["data"]["job"]["id"] == str(terminal.id)
    assert current.json()["data"]["job"]["status"] == "succeeded"


def test_legacy_render_route_submits_async_job_with_successor_headers(
    tmp_path, monkeypatch
) -> None:
    app = create_app(tmp_path)
    project = app.state.project_service.create("legacy render")
    record = app.state.project_service.jobs.enqueue_or_get(
        JobSpec(project_id=project.id, job_type=JobType.EXPORT_PACKAGE, cache_key="legacy")
    ).record
    monkeypatch.setattr(
        app.state.render_job_service,
        "submit",
        lambda project_id: RenderJobSubmission(record, True),
    )

    with TestClient(app) as client:
        response = client.post(f"/api/projects/{project.id}/video/render")

    assert response.status_code == 202
    assert response.headers["Deprecation"] == "true"
    assert response.headers["Link"].startswith(
        f"</api/projects/{project.id}/video/render-jobs>"
    )
    assert response.json()["data"]["job"]["id"] == str(record.id)


def test_render_job_actions_map_illegal_transition_without_internal_details(tmp_path) -> None:
    app = create_app(tmp_path)
    project = app.state.project_service.create("actions")
    record = app.state.project_service.jobs.enqueue_or_get(
        JobSpec(project_id=project.id, job_type=JobType.EXPORT_PACKAGE, cache_key="actions")
    ).record
    with TestClient(app) as client:
        response = client.post(
            f"/api/projects/{project.id}/video/render-jobs/{record.id}/actions",
            json={"action": "retry"},
        )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "render_job_transition_conflict"
    assert response.json()["error"]["message"] == "当前任务不允许执行该操作"
    assert "cannot transition" not in response.text


def test_render_job_ownership_is_project_scoped(tmp_path) -> None:
    app = create_app(tmp_path)
    owner = app.state.project_service.create("owner")
    other = app.state.project_service.create("other")
    record = app.state.project_service.jobs.enqueue_or_get(
        JobSpec(project_id=owner.id, job_type=JobType.EXPORT_PACKAGE, cache_key="owned")
    ).record
    with TestClient(app) as client:
        response = client.get(f"/api/projects/{other.id}/video/render-jobs/{record.id}")

    assert response.status_code == 404
