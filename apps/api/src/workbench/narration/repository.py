from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from workbench.domain.enums import NodeStatus
from workbench.domain.models import AuditEvent, NarrationRecord, PageRecord, ProjectManifest
from workbench.services.project_service import ProjectService


class NarrationRevision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    page_id: UUID
    version: int = Field(ge=1)
    text: str = Field(min_length=1)
    author: str = Field(min_length=1)
    source_refs: list[str] = Field(default_factory=list)
    insufficiencies: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    parent_revision_id: UUID | None = None
    restored_from_revision_id: UUID | None = None
    created_at: datetime
    character_count: int = Field(ge=1)
    estimated_duration_seconds: float = Field(gt=0)


class NarrationEditConflict(RuntimeError):
    pass


class NarrationRepository:
    def __init__(self, projects: ProjectService) -> None:
        self.projects = projects

    def save_revision(
        self,
        project_id: UUID,
        page_id: UUID,
        text: str,
        author: str,
        *,
        expected_revision_id: UUID | None,
        source_refs: list[str] | None = None,
        insufficiencies: list[str] | None = None,
        warnings: list[str] | None = None,
        restored_from_revision_id: UUID | None = None,
    ) -> NarrationRevision:
        clean_text = text.strip()
        clean_author = author.strip()
        if not clean_text or not clean_author:
            raise ValueError("narration text and author are required")
        manifest = self.projects.get(project_id)
        page = _find_page(manifest, page_id)
        current_id = page.narration.revision_id if page.narration else None
        if current_id != expected_revision_id:
            raise NarrationEditConflict("narration revision changed in another editor")

        project_dir = self.projects.workspace_root / manifest.project_dir
        existing = self.list_revisions(project_id, page_id)
        now = datetime.now(UTC)
        character_count = len("".join(clean_text.split()))
        revision = NarrationRevision(
            id=uuid4(),
            page_id=page_id,
            version=len(existing) + 1,
            text=clean_text,
            author=clean_author,
            source_refs=source_refs or [],
            insufficiencies=insufficiencies or [],
            warnings=warnings or [],
            parent_revision_id=current_id,
            restored_from_revision_id=restored_from_revision_id,
            created_at=now,
            character_count=character_count,
            estimated_duration_seconds=round(max(character_count / 4.0, 0.25), 2),
        )
        _write_immutable_revision(project_dir, revision)
        _write_current_revision(project_dir, revision)

        was_confirmed = bool(page.narration and page.narration.confirmed_revision_id)
        page.narration = NarrationRecord(
            id=revision.id,
            revision_id=revision.id,
            text=revision.text,
            status=NodeStatus.NEEDS_CONFIRMATION,
            confirmed_revision_id=None,
            author=revision.author,
            version=revision.version,
            source_refs=revision.source_refs,
            insufficiencies=revision.insufficiencies,
            warnings=revision.warnings,
            updated_at=revision.created_at,
        )
        events = [
            *manifest.audit_log,
            AuditEvent(
                action=(
                    "narration_revision_restored"
                    if restored_from_revision_id
                    else "narration_revision_saved"
                ),
                occurred_at=now,
                details={
                    "page_id": str(page_id),
                    "revision_id": str(revision.id),
                    "version": revision.version,
                    "author": revision.author,
                    "restored_from_revision_id": (
                        str(restored_from_revision_id) if restored_from_revision_id else None
                    ),
                },
            ),
        ]
        if was_confirmed:
            events.append(
                AuditEvent(
                    action="narration_confirmation_invalidated",
                    occurred_at=now,
                    details={"page_id": str(page_id), "revision_id": str(revision.id)},
                )
            )
        self.projects.save(manifest.model_copy(update={"audit_log": events}))
        return revision

    def restore_revision(
        self,
        project_id: UUID,
        page_id: UUID,
        revision_id: UUID,
        actor: str,
        *,
        expected_revision_id: UUID,
    ) -> NarrationRevision:
        target = self.get_revision(project_id, page_id, revision_id)
        return self.save_revision(
            project_id,
            page_id,
            target.text,
            actor,
            expected_revision_id=expected_revision_id,
            source_refs=target.source_refs,
            insufficiencies=target.insufficiencies,
            warnings=target.warnings,
            restored_from_revision_id=target.id,
        )

    def list_revisions(self, project_id: UUID, page_id: UUID) -> list[NarrationRevision]:
        manifest = self.projects.get(project_id)
        _find_page(manifest, page_id)
        history_dir = _history_dir(self.projects.workspace_root / manifest.project_dir, page_id)
        if not history_dir.exists():
            return []
        revisions = [
            NarrationRevision.model_validate_json(path.read_text(encoding="utf-8"))
            for path in history_dir.glob("*.json")
        ]
        return sorted(revisions, key=lambda revision: revision.version)

    def get_revision(self, project_id: UUID, page_id: UUID, revision_id: UUID) -> NarrationRevision:
        manifest = self.projects.get(project_id)
        _find_page(manifest, page_id)
        path = (
            _history_dir(self.projects.workspace_root / manifest.project_dir, page_id)
            / f"{revision_id}.json"
        )
        if not path.is_file():
            raise KeyError(revision_id)
        return NarrationRevision.model_validate_json(path.read_text(encoding="utf-8"))


def _find_page(manifest: ProjectManifest, page_id: UUID) -> PageRecord:
    for page in manifest.pages:
        if page.id == page_id:
            return page
    raise KeyError(page_id)


def _history_dir(project_dir: Path, page_id: UUID) -> Path:
    return project_dir / "04_旁白" / "历史版本" / str(page_id)


def _write_immutable_revision(project_dir: Path, revision: NarrationRevision) -> None:
    history_dir = _history_dir(project_dir, revision.page_id)
    history_dir.mkdir(parents=True, exist_ok=True)
    path = history_dir / f"{revision.id}.json"
    with path.open("x", encoding="utf-8") as handle:
        handle.write(revision.model_dump_json(indent=2))
        handle.flush()
        os.fsync(handle.fileno())


def _write_current_revision(project_dir: Path, revision: NarrationRevision) -> None:
    current_dir = project_dir / "04_旁白" / "当前版本"
    current_dir.mkdir(parents=True, exist_ok=True)
    target = current_dir / f"{revision.page_id}.json"
    temporary = target.with_suffix(".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(revision.model_dump(mode="json"), handle, ensure_ascii=False, indent=2)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, target)
