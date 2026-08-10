from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from uuid import UUID, uuid4

from workbench.audio.alignment import (
    PageNarration,
    align_pages,
    export_page_wavs,
    update_boundary,
)
from workbench.domain.audio import AudioTimeline
from workbench.domain.enums import NodeStatus
from workbench.domain.models import AudioRecord, AuditEvent, PageRecord, ProjectManifest
from workbench.services.project_service import ProjectService


class TimelineService:
    def __init__(self, projects: ProjectService) -> None:
        self.projects = projects

    def build(self, project_id: UUID) -> AudioTimeline:
        manifest = self.projects.get(project_id)
        if manifest.audio_import is None or manifest.transcript is None:
            raise ValueError("请先完成录音导入和本地转写")
        narrations = _confirmed_narrations(manifest.pages)
        if len(narrations) != len(manifest.pages) or not narrations:
            raise ValueError("所有页面必须先确认当前旁白版本")
        timeline = align_pages(
            manifest.transcript,
            narrations,
            silence_intervals_ms=manifest.audio_import.silence_intervals_ms,
            duration_ms=manifest.audio_import.duration_ms,
        )
        self._persist(manifest, timeline, "audio_timeline_built")
        return timeline

    def change_boundary(
        self,
        project_id: UUID,
        boundary_id: UUID,
        time_ms: int,
        version: int,
    ) -> AudioTimeline:
        manifest = self.projects.get(project_id)
        if manifest.audio_timeline is None:
            raise ValueError("请先生成自动分页时间轴")
        timeline = update_boundary(manifest.audio_timeline, boundary_id, time_ms, version)
        self._persist(manifest, timeline, "audio_timeline_boundary_changed")
        return timeline

    def _persist(self, project: ProjectManifest, timeline: AudioTimeline, action: str) -> None:
        if project.audio_import is None:
            raise ValueError("本地录音不存在")
        project_dir = self.projects.workspace_root / project.project_dir
        source = (project_dir / project.audio_import.normalized_relative_path).resolve()
        if project_dir.resolve() not in source.parents or not source.is_file():
            raise ValueError("规范化录音不存在或路径无效")
        assets = export_page_wavs(source, timeline, project_dir / "05_音频" / "分页")
        by_page = {item.page_id: item for item in assets}
        pages = []
        for page in project.pages:
            asset = by_page[page.id]
            relative = asset.path.relative_to(project_dir).as_posix()
            segment = next(item for item in timeline.segments if item.page_id == page.id)
            narration = page.narration
            if narration is None or narration.confirmed_revision_id != narration.revision_id:
                raise ValueError("所有页面必须先确认当前旁白版本")
            cache_key = hashlib.sha256(
                (
                    f"local|{project.audio_import.sha256}|{timeline.id}|{timeline.version}|"
                    f"{segment.start_ms}|{segment.end_ms}|{narration.revision_id}"
                ).encode()
            ).hexdigest()
            pages.append(
                page.model_copy(
                    update={
                        "audio": AudioRecord(
                            id=page.audio.id if page.audio else uuid4(),
                            status=NodeStatus.COMPLETED,
                            source="local",
                            relative_path=relative,
                            duration_ms=asset.duration_ms,
                            cache_key=cache_key,
                            narration_revision_id=narration.revision_id,
                        )
                    }
                )
            )
        now = datetime.now(UTC)
        self.projects.save(
            project.model_copy(
                update={
                    "audio_timeline": timeline,
                    "pages": pages,
                    "audit_log": [
                        *project.audit_log,
                        AuditEvent(
                            action=action,
                            occurred_at=now,
                            details={
                                "timeline_id": str(timeline.id),
                                "version": timeline.version,
                            },
                        ),
                    ],
                }
            )
        )


def _confirmed_narrations(pages: list[PageRecord]) -> list[PageNarration]:
    result: list[PageNarration] = []
    for raw in sorted(pages, key=lambda x: x.order):
        narration = raw.narration
        if narration is None or narration.confirmed_revision_id != narration.revision_id:
            continue
        result.append(PageNarration(raw.id, narration.text))
    return result
