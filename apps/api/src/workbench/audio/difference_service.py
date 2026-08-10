from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from workbench.audio.diff import NarrationText, compare
from workbench.domain.audio import AudioDifference
from workbench.domain.models import AuditEvent
from workbench.services.project_service import ProjectService


class DifferenceService:
    def __init__(self, projects: ProjectService) -> None:
        self.projects = projects

    def compare_project(self, project_id: UUID) -> list[AudioDifference]:
        manifest = self.projects.get(project_id)
        if manifest.transcript is None:
            raise ValueError("请先完成本地录音转写")
        narrations = [
            NarrationText(page_id=page.id, text=page.narration.text)
            for page in sorted(manifest.pages, key=lambda item: item.order)
            if page.narration is not None
            and page.narration.confirmed_revision_id == page.narration.revision_id
        ]
        if len(narrations) != len(manifest.pages) or not narrations:
            raise ValueError("所有页面必须先确认当前旁白版本")
        differences = compare(manifest.transcript, narrations)
        now = datetime.now(UTC)
        self.projects.save(
            manifest.model_copy(
                update={
                    "audio_differences": differences,
                    "audit_log": [
                        *manifest.audit_log,
                        AuditEvent(
                            action="audio_differences_compared",
                            occurred_at=now,
                            details={"difference_count": len(differences)},
                        ),
                    ],
                }
            )
        )
        return differences

    def resolve(self, project_id: UUID, difference_id: UUID, resolution: str) -> AudioDifference:
        manifest = self.projects.get(project_id)
        selected = next(
            (item for item in manifest.audio_differences if item.id == difference_id), None
        )
        if selected is None:
            raise KeyError(difference_id)
        if resolution not in {"accept_recording", "change_narration", "reimport"}:
            raise ValueError("无效的差异处理方式")
        now = datetime.now(UTC)
        updated = selected.model_copy(
            update={"status": "resolved", "resolution": resolution, "resolved_at": now}
        )
        self.projects.save(
            manifest.model_copy(
                update={
                    "audio_differences": [
                        updated if item.id == difference_id else item
                        for item in manifest.audio_differences
                    ],
                    "audit_log": [
                        *manifest.audit_log,
                        AuditEvent(
                            action="audio_difference_resolved",
                            occurred_at=now,
                            details={
                                "difference_id": str(difference_id),
                                "resolution": resolution,
                            },
                        ),
                    ],
                }
            )
        )
        return updated
