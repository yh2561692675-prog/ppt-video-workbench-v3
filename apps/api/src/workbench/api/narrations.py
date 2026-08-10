from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from pydantic import BaseModel, ConfigDict, Field

from workbench.api.projects import Envelope, envelope
from workbench.integrations.llm.client import LlmIntegrationError
from workbench.narration.generator import NarrationGenerationError
from workbench.narration.importer import (
    ImportMethod,
    NarrationImportError,
    NarrationImportPreview,
    preview_import,
)
from workbench.narration.repository import (
    NarrationEditConflict,
    NarrationRepository,
    NarrationRevision,
)
from workbench.services.narration_generation_service import NarrationGenerationService


class RevisionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1)
    author: str = Field(min_length=1, max_length=80)
    expected_revision_id: UUID | None
    source_refs: list[str] = Field(default_factory=list)
    insufficiencies: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class RevisionRestore(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actor: str = Field(min_length=1, max_length=80)
    expected_revision_id: UUID


class NarrationGenerate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile_id: UUID


class NarrationImportCommitAssignment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page_id: UUID
    text: str = Field(min_length=1)
    expected_revision_id: UUID | None = None
    method: ImportMethod
    warning: str | None = None


class NarrationImportCommit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_name: str = Field(min_length=1, max_length=255)
    assignments: list[NarrationImportCommitAssignment]


def create_narrations_router(
    repository: NarrationRepository,
    generation: NarrationGenerationService,
) -> APIRouter:
    router = APIRouter(prefix="/api/projects/{project_id}/narrations")

    @router.post(
        "/import/preview",
        response_model=Envelope[NarrationImportPreview],
    )
    async def preview_narration_import(
        project_id: UUID, file: Annotated[UploadFile, File()]
    ) -> Envelope[NarrationImportPreview]:
        try:
            manifest = repository.projects.get(project_id)
            content = await file.read()
            preview = preview_import(file.filename or "narration.txt", content, manifest.pages)
        except KeyError as error:
            raise HTTPException(status_code=404, detail="project not found") from error
        except NarrationImportError as error:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "narration_import_rejected",
                    "message": str(error),
                    "action": "璇锋鏌ョ巼浠剁被鍨嬪拰鏃佺櫧鏍煎紡鍚庨噸璇",
                },
            ) from error
        return envelope(preview)

    @router.post(
        "/import/commit",
        status_code=status.HTTP_201_CREATED,
        response_model=Envelope[list[NarrationRevision]],
    )
    def commit_narration_import(
        project_id: UUID, request: NarrationImportCommit
    ) -> Envelope[list[NarrationRevision]]:
        try:
            manifest = repository.projects.get(project_id)
            page_ids = {page.id for page in manifest.pages}
            if any(item.page_id not in page_ids for item in request.assignments):
                raise KeyError("page")
            revisions = [
                repository.save_revision(
                    project_id,
                    item.page_id,
                    item.text,
                    "narration-import",
                    expected_revision_id=item.expected_revision_id,
                    source_refs=[request.source_name],
                    warnings=[item.warning] if item.warning else [],
                )
                for item in request.assignments
            ]
        except NarrationEditConflict as error:
            raise _conflict() from error
        except KeyError as error:
            raise HTTPException(status_code=404, detail="project or page not found") from error
        return envelope(revisions)

    @router.post(
        "/{page_id}/generate",
        status_code=status.HTTP_201_CREATED,
        response_model=Envelope[NarrationRevision],
    )
    def generate_narration(
        project_id: UUID, page_id: UUID, request: NarrationGenerate
    ) -> Envelope[NarrationRevision]:
        try:
            return envelope(generation.generate(project_id, page_id, request.profile_id))
        except LlmIntegrationError as error:
            raise HTTPException(
                status_code=422,
                detail={"code": error.code, "message": str(error), "action": error.action},
            ) from error
        except NarrationGenerationError as error:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": error.code,
                    "message": str(error),
                    "action": "请检查当前页材料与模型输出后重试",
                },
            ) from error
        except NarrationEditConflict as error:
            raise _conflict() from error
        except KeyError as error:
            raise HTTPException(
                status_code=404, detail="project, page or profile not found"
            ) from error

    @router.post(
        "/{page_id}/revisions",
        status_code=status.HTTP_201_CREATED,
        response_model=Envelope[NarrationRevision],
    )
    def save_revision(
        project_id: UUID, page_id: UUID, request: RevisionCreate
    ) -> Envelope[NarrationRevision]:
        try:
            revision = repository.save_revision(
                project_id,
                page_id,
                request.text,
                request.author,
                expected_revision_id=request.expected_revision_id,
                source_refs=request.source_refs,
                insufficiencies=request.insufficiencies,
                warnings=request.warnings,
            )
        except NarrationEditConflict as error:
            raise _conflict() from error
        except KeyError as error:
            raise HTTPException(status_code=404, detail="project or page not found") from error
        return envelope(revision)

    @router.get("/{page_id}/revisions", response_model=Envelope[list[NarrationRevision]])
    def list_revisions(project_id: UUID, page_id: UUID) -> Envelope[list[NarrationRevision]]:
        try:
            return envelope(repository.list_revisions(project_id, page_id))
        except KeyError as error:
            raise HTTPException(status_code=404, detail="project or page not found") from error

    @router.post("/{page_id}/restore/{revision_id}", response_model=Envelope[NarrationRevision])
    def restore_revision(
        project_id: UUID,
        page_id: UUID,
        revision_id: UUID,
        request: RevisionRestore,
    ) -> Envelope[NarrationRevision]:
        try:
            return envelope(
                repository.restore_revision(
                    project_id,
                    page_id,
                    revision_id,
                    request.actor,
                    expected_revision_id=request.expected_revision_id,
                )
            )
        except NarrationEditConflict as error:
            raise _conflict() from error
        except KeyError as error:
            raise HTTPException(status_code=404, detail="revision not found") from error

    return router


def _conflict() -> HTTPException:
    return HTTPException(
        status_code=409,
        detail={
            "code": "narration_edit_conflict",
            "message": "旁白已在另一个窗口更新",
            "action": "请刷新当前页面，比较新版本后再保存",
        },
    )
