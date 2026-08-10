from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from workbench.domain.effects import EffectPlanRecord, calculate_plan_hash, validate_record_hash
from workbench.domain.models import PageRecord
from workbench.services.project_service import ProjectService

from .catalog import EFFECT_CATALOG, EFFECT_CATALOG_VERSION
from .planner import EffectPlanner, EffectPlanningInput
from .schema import EffectPlanV2


class EffectMutationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: UUID
    changed_page_ids: list[UUID] = Field(default_factory=list)
    skipped_page_ids: list[UUID] = Field(default_factory=list)
    blocked_page_ids: list[UUID] = Field(default_factory=list)


class EffectWorkspacePage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page_id: UUID
    page_order: int
    title: str | None
    record: object | None


class EffectWorkspaceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    policy: object
    catalog_version: str
    pages: list[EffectWorkspacePage]


class EffectService:
    def __init__(self, projects: ProjectService, planner: EffectPlanner | None = None) -> None:
        self.projects = projects
        self.planner = planner or EffectPlanner()

    def catalog(self) -> dict[str, object]:
        return {"catalog_version": EFFECT_CATALOG_VERSION, "templates": EFFECT_CATALOG}

    def get_workspace(self, project_id: UUID) -> EffectWorkspaceResponse:
        project = self.projects.get(project_id)
        return EffectWorkspaceResponse(
            policy=project.effect_policy,
            catalog_version=EFFECT_CATALOG_VERSION,
            pages=[
                EffectWorkspacePage(
                    page_id=page.id,
                    page_order=page.order,
                    title=page.title,
                    record=page.effect_plan,
                )
                for page in sorted(project.pages, key=lambda item: item.order)
            ],
        )

    def generate(
        self,
        project_id: UUID,
        *,
        page_ids: list[UUID] | None = None,
        force: bool = False,
    ) -> EffectMutationResult:
        project = self.projects.get(project_id)
        requested = set(page_ids) if page_ids else {page.id for page in project.pages}
        changed: list[UUID] = []
        skipped: list[UUID] = []
        blocked: list[UUID] = []
        pages: list[PageRecord] = []
        for page in project.pages:
            if page.id not in requested:
                pages.append(page)
                continue
            if page.effect_plan is not None and page.effect_plan.locked:
                blocked.append(page.id)
                pages.append(page)
                continue
            duration_ms = page.timeline.end_ms - page.timeline.start_ms if page.timeline else 1_000
            input_data = EffectPlanningInput(
                page_id=str(page.id),
                page_type="title" if page.order == 1 else "content",
                duration_ms=max(duration_ms, 1),
                title=page.title or "",
                aspect_ratio=project.effect_policy.aspect_ratio,
                default_strength=project.effect_policy.default_strength,
                catalog_version=project.effect_policy.catalog_version,
            )
            record = self.planner.reconcile(input_data, page.effect_plan, force=force)
            if page.effect_plan is not None and record.plan_hash == page.effect_plan.plan_hash:
                skipped.append(page.id)
            else:
                changed.append(page.id)
            pages.append(page.model_copy(update={"effect_plan": record}))
        if changed:
            project = self.projects.save(
                project.model_copy(update={"pages": pages, "updated_at": datetime.now(UTC)})
            )
        return EffectMutationResult(
            project_id=project_id,
            changed_page_ids=changed,
            skipped_page_ids=skipped,
            blocked_page_ids=blocked,
        )

    def update_page(
        self,
        project_id: UUID,
        page_id: UUID,
        *,
        expected_revision: int,
        plan: EffectPlanV2,
        locked: bool,
    ) -> EffectPlanRecord:
        project = self.projects.get(project_id)
        page = next((item for item in project.pages if item.id == page_id), None)
        if page is None:
            raise KeyError(page_id)
        current = page.effect_plan
        if current is not None and current.revision != expected_revision:
            raise ValueError("effect_revision_conflict")
        record = EffectPlanRecord(
            revision=(current.revision + 1 if current else 1),
            plan=plan,
            plan_hash=calculate_plan_hash(plan),
            input_fingerprint=(current.input_fingerprint if current else "0" * 64),
            source="manual",
            status="ready",
            locked=locked,
            confidence=1.0,
            updated_at=datetime.now(UTC),
        )
        validate_record_hash(record)
        pages = [
            item.model_copy(update={"effect_plan": record}) if item.id == page_id else item
            for item in project.pages
        ]
        self.projects.save(project.model_copy(update={"pages": pages}))
        return record

    def unlock_page(
        self, project_id: UUID, page_id: UUID, *, expected_revision: int
    ) -> EffectPlanRecord:
        project = self.projects.get(project_id)
        page = next((item for item in project.pages if item.id == page_id), None)
        if page is None or page.effect_plan is None:
            raise KeyError(page_id)
        if page.effect_plan.revision != expected_revision:
            raise ValueError("effect_revision_conflict")
        record = page.effect_plan.model_copy(
            update={
                "revision": page.effect_plan.revision + 1,
                "locked": False,
                "updated_at": datetime.now(UTC),
            }
        )
        pages = [
            item.model_copy(update={"effect_plan": record}) if item.id == page_id else item
            for item in project.pages
        ]
        self.projects.save(project.model_copy(update={"pages": pages}))
        return record
