from __future__ import annotations

from pathlib import Path
from uuid import UUID

from workbench.audio.service import AudioService
from workbench.domain.models import ProjectManifest
from workbench.subtitles.models import SubtitleTimeline
from workbench.video.models import ProjectVideoProps, VideoPageProps


class VideoPropsService:
    def __init__(self, audio: AudioService) -> None:
        self.audio = audio

    def build(
        self,
        project: ProjectManifest,
        subtitles: SubtitleTimeline,
    ) -> ProjectVideoProps:
        page_audio = {item.page_id: item for item in self.audio.resolve_page_audio(project)}
        segments = (
            {segment.page_id: segment for segment in project.audio_timeline.segments}
            if project.audio_timeline is not None
            else {}
        )
        pages = []
        cursor_ms = 0
        for page in sorted(project.pages, key=lambda item: item.order):
            audio = page_audio[page.id]
            segment = segments.get(page.id)
            if segment is None:
                start_ms, end_ms = cursor_ms, cursor_ms + audio.duration_ms
            else:
                start_ms, end_ms = segment.start_ms, segment.end_ms
            pages.append(
                VideoPageProps(
                    page_id=page.id,
                    page_order=page.order,
                    title=page.title or "",
                    image_path=self._page_image_path(project, page.id),
                    audio_path=audio.path,
                    start_ms=start_ms,
                    end_ms=end_ms,
                    subtitle_cue_ids=[cue.id for cue in subtitles.cues if cue.page_id == page.id],
                    effect_plan=page.effect_plan.plan if page.effect_plan else None,
                    effect_plan_revision=page.effect_plan.revision if page.effect_plan else None,
                    effect_plan_hash=(page.effect_plan.plan_hash if page.effect_plan else None),
                )
            )
            cursor_ms = end_ms
        all_effects_ready = bool(pages) and all(item.effect_plan is not None for item in pages)
        return ProjectVideoProps(
            project_id=project.id,
            duration_ms=subtitles.duration_ms,
            schema_version=2 if all_effects_ready else 1,
            width=1080 if project.effect_policy.aspect_ratio == "9:16" else 1920,
            height=1920 if project.effect_policy.aspect_ratio == "9:16" else 1080,
            template_version="effect-engine-v2" if all_effects_ready else "tech-board-v1",
            catalog_version=project.effect_policy.catalog_version if all_effects_ready else None,
            pages=pages,
            subtitles=subtitles.cues,
        )

    def _page_image_path(self, project: ProjectManifest, page_id: UUID) -> str:
        extraction = next(
            (
                item
                for item in project.page_extractions
                if (
                    page_source_id := next(
                        (page.source_file_id for page in project.pages if page.id == page_id), None
                    )
                )
                and item.id == page_source_id
            ),
            None,
        )
        if extraction is None:
            page = next((item for item in project.pages if item.id == page_id), None)
            extraction = next(
                (item for item in project.page_extractions if page and item.order == page.order),
                None,
            )
        if extraction is None or extraction.preview_path is None:
            raise ValueError("页面缺少可用于视频的预览图")
        root = (self.audio.workspace_root / project.project_dir).resolve()
        stored_path = Path(extraction.preview_path)
        path = (stored_path if stored_path.is_absolute() else root / stored_path).resolve()
        if not path.is_relative_to(root):
            raise ValueError("页面预览图路径超出项目目录")
        return str(path.relative_to(root))
