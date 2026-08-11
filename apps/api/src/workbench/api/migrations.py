from __future__ import annotations

import json
from pathlib import Path
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from workbench.api.projects import Envelope, envelope
from workbench.migrations.project_v2 import (
    ProjectMigrationError,
    ProjectMigrationPlan,
    ProjectMigrationResult,
    ProjectV2Migration,
)
from workbench.rendering.legacy_adapter import LegacyFallbackForbidden
from workbench.rendering.project_reader import ProjectRenderSource, ProjectRenderSourceReader
from workbench.services.project_service import ProjectService
from workbench.storage.workspace_db import projects as projects_table


class MigrationRollbackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


def create_migrations_router(projects: ProjectService) -> APIRouter:
    router = APIRouter(prefix="/api/projects/{project_id}")

    @router.get("/render-source", response_model=Envelope[ProjectRenderSource])
    def render_source(
        project_id: UUID,
        renderer_generation: Literal["v1", "v2"] = "v1",
        migration_enabled: bool = True,
    ) -> Envelope[ProjectRenderSource]:
        root, payload = load_raw_project(projects, project_id)
        try:
            return envelope(
                ProjectRenderSourceReader(root).open(
                    payload,
                    renderer_generation=renderer_generation,
                    migration_enabled=migration_enabled,
                )
            )
        except LegacyFallbackForbidden as error:
            raise HTTPException(
                status_code=409,
                detail={"code": "v2_legacy_fallback_forbidden", "message": str(error)},
            ) from error

    @router.post(
        "/migrations/v2/preview",
        response_model=Envelope[ProjectMigrationPlan],
    )
    def preview_migration(project_id: UUID) -> Envelope[ProjectMigrationPlan]:
        root, payload = load_raw_project(projects, project_id)
        return envelope(ProjectV2Migration(root).preview(payload))

    @router.post(
        "/migrations/v2/execute",
        response_model=Envelope[ProjectMigrationResult],
    )
    def execute_migration(
        project_id: UUID, plan: ProjectMigrationPlan
    ) -> Envelope[ProjectMigrationResult]:
        root, payload = load_raw_project(projects, project_id)
        if plan.project_id != project_id:
            raise HTTPException(status_code=422, detail="migration project id mismatch")
        try:
            return envelope(ProjectV2Migration(root).execute(plan, payload))
        except ProjectMigrationError as error:
            raise HTTPException(
                status_code=409,
                detail={"code": "project_v2_migration_blocked", "message": str(error)},
            ) from error

    @router.post("/migrations/v2/rollback", response_model=Envelope[dict[str, object]])
    def rollback_migration(
        project_id: UUID, request: MigrationRollbackRequest
    ) -> Envelope[dict[str, object]]:
        root, _ = load_raw_project(projects, project_id)
        try:
            ProjectV2Migration(root).rollback(request.plan_hash)
        except ProjectMigrationError as error:
            raise HTTPException(
                status_code=409,
                detail={"code": "project_v2_rollback_blocked", "message": str(error)},
            ) from error
        return envelope({"rolled_back": True, "plan_hash": request.plan_hash})

    return router


def load_raw_project(
    projects: ProjectService, project_id: UUID
) -> tuple[Path, dict[str, object]]:
    with projects.database.connect() as connection:
        project_dir = connection.execute(
            select(projects_table.c.project_dir).where(
                projects_table.c.id == str(project_id)
            )
        ).scalar_one_or_none()
    if project_dir is None:
        raise HTTPException(status_code=404, detail="project not found")
    root = (projects.workspace_root / str(project_dir)).resolve()
    payload = json.loads((root / "project.json").read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or str(payload.get("id")) != str(project_id):
        raise HTTPException(status_code=422, detail="project manifest identity mismatch")
    return root, payload
