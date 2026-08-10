from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from workbench.domain.models import ProjectManifest, VideoPreflightRecord
from workbench.services.project_service import ProjectService
from workbench.subtitles.models import SubtitleBuildError
from workbench.subtitles.service import SubtitleService

from .avoidance import choose_subtitle_placement
from .models import PreflightIssue, ProjectVideoProps, SubtitlePlacement, TextRect, VideoPreflight
from .props_service import VideoPropsService


class VideoPreviewService:
    def __init__(
        self,
        projects: ProjectService,
        subtitles: SubtitleService,
        props: VideoPropsService,
    ) -> None:
        self.projects = projects
        self.subtitles = subtitles
        self.props = props

    def preflight(self, project_id: UUID, *, reduced_motion: bool | None = None) -> VideoPreflight:
        project = self.projects.get(project_id)
        effective_reduced_motion = (
            reduced_motion
            if reduced_motion is not None
            else project.video_preflight.reduced_motion
            if project.video_preflight is not None
            else False
        )
        return self.preflight_project(project, reduced_motion=effective_reduced_motion)

    def can_enter_render(self, project: ProjectManifest) -> bool:
        return self.preflight_project(
            project,
            reduced_motion=(
                project.video_preflight.reduced_motion
                if project.video_preflight is not None
                else False
            ),
        ).allowed

    def preflight_project(
        self, project: ProjectManifest, *, reduced_motion: bool = False
    ) -> VideoPreflight:
        audio_gate = self.subtitles.audio_gate.can_enter_subtitles(project)
        if not audio_gate.allowed:
            result = VideoPreflight(
                allowed=False,
                issues=[
                    PreflightIssue(
                        code=reason.code,
                        message=reason.message,
                        action=reason.action,
                        page_id=reason.page_id,
                    )
                    for reason in audio_gate.reasons
                ],
            )
            return self._persist(project, result, reduced_motion=reduced_motion)
        try:
            subtitles = self.subtitles.get(project.id)
            props = self.props.build(project, subtitles)
        except (KeyError, SubtitleBuildError, ValueError) as error:
            result = VideoPreflight(
                allowed=False,
                issues=[
                    PreflightIssue(
                        code="video_preflight_incomplete",
                        message=str(error),
                        action="请先生成字幕并补齐页面预览图后重新预检",
                    )
                ],
            )
            return self._persist(project, result, reduced_motion=reduced_motion)

        placements = self._placements(project, props)
        resolved_props = props.model_copy(
            update={
                "reduced_motion": reduced_motion,
                "subtitle_placements": placements,
            }
        )
        return self._persist(
            project,
            VideoPreflight(allowed=True, props=resolved_props, placements=placements),
            reduced_motion=reduced_motion,
        )

    def preview(self, project_id: UUID) -> VideoPreflight:
        return self.preflight(project_id)

    def preview_asset(self, project_id: UUID, relative_path: str) -> Path:
        project = self.projects.get(project_id)
        root = (self.projects.workspace_root / project.project_dir).resolve()
        candidate = (root / relative_path).resolve()
        if root not in candidate.parents or not candidate.is_file():
            raise FileNotFoundError(relative_path)
        return candidate

    def _placements(
        self, project: ProjectManifest, props: ProjectVideoProps
    ) -> list[SubtitlePlacement]:
        placements: list[SubtitlePlacement] = []
        for page in props.pages:
            cues = [cue for cue in props.subtitles if cue.page_id == page.page_id]
            if not cues:
                continue
            occupied = self._occupied_rects(project, page.page_id)
            placements.append(
                choose_subtitle_placement(
                    occupied,
                    page_id=page.page_id,
                    subtitle_width=1_300,
                    subtitle_height=96,
                )
            )
        return placements

    def _occupied_rects(self, project: ProjectManifest, page_id: UUID) -> list[TextRect]:
        page = next((item for item in project.pages if item.id == page_id), None)
        extraction = next(
            (
                item
                for item in project.page_extractions
                if page
                and (
                    (page.source_file_id and item.id == page.source_file_id)
                    or item.order == page.order
                )
            ),
            None,
        )
        if extraction is None:
            return []
        return [
            TextRect(
                x=max(0, span.bbox[0]),
                y=max(0, span.bbox[1]),
                width=max(1, span.bbox[2] - span.bbox[0]),
                height=max(1, span.bbox[3] - span.bbox[1]),
            )
            for span in extraction.spans
        ]

    def _persist(
        self,
        project: ProjectManifest,
        result: VideoPreflight,
        *,
        reduced_motion: bool,
    ) -> VideoPreflight:
        props_cache_key = (
            hashlib.sha256(result.props.model_dump_json().encode("utf-8")).hexdigest()
            if result.props is not None
            else None
        )
        record = VideoPreflightRecord(
            id=uuid4(),
            allowed=result.allowed,
            issue_codes=[issue.code for issue in result.issues],
            props_cache_key=props_cache_key,
            reduced_motion=reduced_motion,
            checked_at=datetime.now(UTC),
        )
        self.projects.save(project.model_copy(update={"video_preflight": record}))
        return result
