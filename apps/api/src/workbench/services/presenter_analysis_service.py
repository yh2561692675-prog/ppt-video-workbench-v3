from __future__ import annotations

import hashlib
import os
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from workbench.asr.presenter_transcriber import (
    PresenterTranscriptionBackend,
    transcribe_presenter,
)
from workbench.audio.models import WhisperModelManager
from workbench.audio.transcriber import FasterWhisperBackend
from workbench.domain.audio import SubtitleArtifact
from workbench.domain.models import AuditEvent, ProjectManifest
from workbench.domain.occupancy import PageOccupancyMap
from workbench.domain.transcript import TranscriptRevision
from workbench.layout.presenter_placement import PresenterCue, plan_presenter_segments
from workbench.matching.presenter_slide_matcher import (
    PresenterMatchPage,
    PresenterMatchResult,
    match_presenter_to_slides,
)
from workbench.media.presenter_audio import AnalysisAudio, extract_analysis_audio
from workbench.subtitles.models import SubtitleTimeline
from workbench.subtitles.service import format_srt
from workbench.timeline.presenter_adapters import to_caption_cues
from workbench.timeline.presenter_builder import build_presenter_timeline, timeline_content_hash

from .project_service import ProjectService

PresenterAudioExtractor = Callable[[Path, Path], AnalysisAudio]


class PresenterAnalysisError(RuntimeError):
    pass


class PresenterAnalysisUnavailable(PresenterAnalysisError):
    pass


class PresenterAnalysisResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project: ProjectManifest
    transcript: TranscriptRevision
    matches: PresenterMatchResult


class PresenterAnalysisService:
    def __init__(
        self,
        projects: ProjectService,
        *,
        backend: PresenterTranscriptionBackend | None = None,
        models: WhisperModelManager | None = None,
        audio_extractor: PresenterAudioExtractor | None = None,
    ) -> None:
        self.projects = projects
        self.backend = backend
        self.models = models
        self.audio_extractor: PresenterAudioExtractor = audio_extractor or extract_analysis_audio

    def analyze(self, project_id: UUID) -> PresenterAnalysisResult:
        project = self.projects.get(project_id)
        source = project.presenter_source
        if source is None:
            raise PresenterAnalysisError("presenter source is required")
        if not project.pages:
            raise PresenterAnalysisError("presenter analysis requires imported PPT pages")
        root = (self.projects.workspace_root / project.project_dir).resolve()
        source_path = (root / source.relative_path).resolve()
        if not source_path.is_relative_to(root) or not source_path.is_file():
            raise PresenterAnalysisError("presenter source path is invalid")
        backend, backend_options = self._resolve_backend()
        audio_path = root / "05_音频" / "presenter-analysis.wav"
        audio = self.audio_extractor(source_path, audio_path)
        transcript = transcribe_presenter(
            audio,
            backend,
            source_hash=source.sha256,
            backend_options=backend_options,
        )
        extraction_by_order = {item.order: item for item in project.page_extractions}
        pages = [
            PresenterMatchPage(
                page_id=page.id,
                page_index=page.order - 1,
                title=page.title or "",
                slide_text=(
                    extraction_by_order[page.order].text
                    if page.order in extraction_by_order
                    else ""
                ),
                narration_text=page.narration.text if page.narration else "",
            )
            for page in sorted(project.pages, key=lambda item: item.order)
        ]
        locked = {
            sentence_id: anchor.page_id
            for anchor in (project.presenter_timeline.anchors if project.presenter_timeline else [])
            if anchor.manual_lock
            for sentence_id in anchor.sentence_ids
        }
        matches = match_presenter_to_slides(transcript.sentences, pages, locked=locked)
        timeline = build_presenter_timeline(
            matches,
            transcript.sentences,
            source.duration_ms,
            source_id=source.id,
            source_version=source.sha256,
        )
        timeline = timeline.model_copy(
            update={
                "segments": plan_presenter_segments(
                    PageOccupancyMap(),
                    [
                        PresenterCue(start_ms=anchor.start_ms, end_ms=anchor.end_ms)
                        for anchor in timeline.anchors
                    ],
                    aspect=project.effect_policy.aspect_ratio,
                )
            }
        )
        timeline = timeline.model_copy(update={"timeline_hash": timeline_content_hash(timeline)})
        subtitle_timeline = SubtitleTimeline(
            duration_ms=timeline.duration_ms,
            cues=to_caption_cues(transcript, timeline.anchors),
        )
        subtitle_timeline_bytes = (subtitle_timeline.model_dump_json(indent=2) + "\n").encode(
            "utf-8"
        )
        subtitle_srt_bytes = format_srt(subtitle_timeline).encode("utf-8")
        subtitle_timeline_path = root / "06_字幕" / "字幕时间轴.json"
        subtitle_srt_path = root / "06_字幕" / "字幕.srt"
        self._write_bytes(subtitle_timeline_path, subtitle_timeline_bytes)
        self._write_bytes(subtitle_srt_path, subtitle_srt_bytes)
        subtitle_artifact = SubtitleArtifact(
            timeline_relative_path="06_字幕/字幕时间轴.json",
            srt_relative_path="06_字幕/字幕.srt",
            timeline_sha256=hashlib.sha256(subtitle_timeline_bytes).hexdigest(),
            srt_sha256=hashlib.sha256(subtitle_srt_bytes).hexdigest(),
        )
        payload = project.model_dump(mode="python")
        payload["presenter_timeline"] = timeline
        payload["subtitle_artifact"] = subtitle_artifact
        payload["audit_log"] = [
            *project.audit_log,
            AuditEvent(
                action="presenter_analysis_completed",
                occurred_at=datetime.now(UTC),
                details={
                    "transcript_hash": transcript.content_hash,
                    "timeline_hash": timeline.timeline_hash,
                    "timeline_revision": timeline.revision,
                },
            ),
        ]
        saved = self.projects.save(ProjectManifest.model_validate(payload))
        artifact_root = root / "03_文字识别" / "presenter"
        self._write_json(artifact_root / "transcript.json", transcript.model_dump_json(indent=2))
        self._write_json(artifact_root / "matches.json", matches.model_dump_json(indent=2))
        self._write_json(artifact_root / "timeline.json", timeline.model_dump_json(indent=2))
        return PresenterAnalysisResult(project=saved, transcript=transcript, matches=matches)

    def _resolve_backend(self) -> tuple[PresenterTranscriptionBackend, dict[str, object]]:
        if self.backend is not None:
            return self.backend, {}
        if self.models is None or not self.models.is_available("small"):
            raise PresenterAnalysisUnavailable("local presenter ASR model small is unavailable")
        return FasterWhisperBackend(), {
            "model_path": self.models.model_path("small"),
            "device": "cpu",
            "compute_type": "int8",
        }

    @staticmethod
    def _write_json(target: Path, payload: str) -> None:
        PresenterAnalysisService._write_bytes(target, (payload + "\n").encode("utf-8"))

    @staticmethod
    def _write_bytes(target: Path, payload: bytes) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(f".{target.name}.tmp")
        try:
            with temporary.open("wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)
