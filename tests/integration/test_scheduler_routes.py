from __future__ import annotations

from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
from workbench.api.scheduler import create_scheduler_router
from workbench.scheduler.service import BatchSchedulerService


def test_scheduler_routes_create_and_gate_night_queue(tmp_path):
    project_id = uuid4()
    app = FastAPI()
    app.include_router(
        create_scheduler_router(
            BatchSchedulerService(
                tmp_path,
                project_dir_resolver=lambda _: "project",
                preset_exists=lambda _: True,
            )
        )
    )
    with TestClient(app) as client:
        created = client.post(
            f"/api/projects/{project_id}/batch-productions",
            json={"preset_ids": ["master-1080p-30"], "night_queue": True},
        )
        assert created.status_code == 201
        batch_id = created.json()["data"]["batch_id"]
        batches = client.get(f"/api/projects/{project_id}/batch-productions")
        assert batches.status_code == 200
        dispatch = client.post(
            f"/api/projects/{project_id}/batch-productions/{batch_id}/dispatch",
            json={"allow_night": False},
        )
        assert dispatch.status_code == 409
