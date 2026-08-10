from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import NAMESPACE_URL, UUID, uuid5

from workbench.audio.models import Transcript, TranscriptSegment, TranscriptWord
from workbench.audio.service import AudioService
from workbench.domain.audio import SubtitleArtifact
from workbench.domain.confirmation import GateReason
from workbench.domain.models import AuditEvent, ProjectManifest
from workbench.services.project_service import ProjectService
from workbench.workflow.audio_gate import AudioGateService

from .models import SubtitleBuildError, SubtitleCue, SubtitlePageRange, SubtitleTimeline


class SubtitleGateBlocked(SubtitleBuildError):
    def __init__(self, reasons: list[GateReason]) -> None:
        super().__init__("音频路线尚未通过字幕门禁")
        self.reasons = reasons


@dataclass(frozen=True)
class _Fragment:
    page: SubtitlePageRange
    word_index: int
    text: str
    start_ms: int
    end_ms: int
    clipped: bool


class SubtitleService:
    def __init__(
        self,
        projects: ProjectService,
        audio_gate: AudioGateService,
        audio: AudioService,
    ) -> None:
        self.projects = projects
        self.audio_gate = audio_gate
        self.audio = audio

    def build(self, project_id: UUID) -> SubtitleTimeline:
        project = self.projects.get(project_id)
        gate = self.audio_gate.can_enter_subtitles(project)
        if not gate.allowed:
            raise SubtitleGateBlocked(gate.reasons)
        transcript = project.transcript
        if transcript is None:
            transcript = self._build_heygen_transcript(project)
            if transcript is None:
                raise SubtitleBuildError("缺少本地转写的词级时间戳")
            project = project.model_copy(
                update={
                    "transcript": transcript,
                    "audit_log": [
                        *project.audit_log,
                        AuditEvent(
                            action="heygen_subtitle_timestamps_built",
                            occurred_at=datetime.now(UTC),
                            details={"word_count": len(transcript.words)},
                        ),
                    ],
                }
            )
            self.projects.save(project)
        ranges, duration_ms = self._page_ranges(project)
        timeline = build_subtitle_timeline(
            ranges,
            transcript.words,
            duration_ms=duration_ms,
        )
        root = self.projects.workspace_root / project.project_dir
        folder = root / "06_字幕"
        folder.mkdir(parents=True, exist_ok=True)
        timeline_path = folder / "字幕时间轴.json"
        srt_path = folder / "字幕.srt"
        timeline_bytes = (timeline.model_dump_json(indent=2) + "\n").encode("utf-8")
        srt_bytes = format_srt(timeline).encode("utf-8")
        _atomic_write(timeline_path, timeline_bytes)
        _atomic_write(srt_path, srt_bytes)
        artifact = SubtitleArtifact(
            timeline_relative_path="06_字幕/字幕时间轴.json",
            srt_relative_path="06_字幕/字幕.srt",
            timeline_sha256=hashlib.sha256(timeline_bytes).hexdigest(),
            srt_sha256=hashlib.sha256(srt_bytes).hexdigest(),
        )
        self.projects.save(project.model_copy(update={"subtitle_artifact": artifact}))
        return timeline

    def _build_heygen_transcript(self, project: ProjectManifest) -> Transcript | None:
        if {page.audio.source for page in project.pages if page.audio is not None} != {"heygen"}:
            return None
        ranges, _ = self._page_ranges(project)
        text_by_page = {
            page.id: page.narration.text
            for page in project.pages
            if page.narration is not None
            and page.narration.confirmed_revision_id == page.narration.revision_id
        }
        words = build_heygen_word_timestamps(ranges, text_by_page)
        segments = [
            TranscriptSegment(
                text=text_by_page[page.page_id],
                start_ms=page.start_ms,
                end_ms=page.end_ms,
                words=[word for word in words if page.start_ms <= word.start_ms < page.end_ms],
            )
            for page in ranges
        ]
        return Transcript(
            segments=segments,
            words=words,
            detected_language="zh",
            model="heygen_text_alignment",
            device="remote",
        )

    def get(self, project_id: UUID) -> SubtitleTimeline:
        project = self.projects.get(project_id)
        if project.subtitle_artifact is None:
            raise KeyError(project_id)
        path = self._safe_path(project, project.subtitle_artifact.timeline_relative_path)
        if not path.is_file():
            raise KeyError(project_id)
        return SubtitleTimeline.model_validate_json(path.read_text(encoding="utf-8"))

    def _page_ranges(self, project: ProjectManifest) -> tuple[list[SubtitlePageRange], int]:
        if project.audio_timeline is not None:
            segments = {segment.page_id: segment for segment in project.audio_timeline.segments}
            ranges = [
                SubtitlePageRange(
                    page_id=page.id,
                    page_order=page.order,
                    start_ms=segments[page.id].start_ms,
                    end_ms=segments[page.id].end_ms,
                )
                for page in sorted(project.pages, key=lambda item: item.order)
                if page.id in segments
            ]
            return ranges, project.audio_timeline.duration_ms

        page_audio = self.audio.resolve_page_audio(project)
        audio_by_page = {item.page_id: item for item in page_audio}
        start_ms = 0
        ranges = []
        for page in sorted(project.pages, key=lambda item: item.order):
            duration_ms = audio_by_page[page.id].duration_ms
            ranges.append(
                SubtitlePageRange(
                    page_id=page.id,
                    page_order=page.order,
                    start_ms=start_ms,
                    end_ms=start_ms + duration_ms,
                )
            )
            start_ms += duration_ms
        return ranges, start_ms

    def _safe_path(self, project: ProjectManifest, relative_path: str) -> Path:
        root = (self.projects.workspace_root / project.project_dir).resolve()
        target = (root / relative_path).resolve()
        if root not in target.parents:
            raise SubtitleBuildError("字幕路径超出项目目录")
        return target


def build_subtitle_timeline(
    pages: list[SubtitlePageRange],
    words: list[TranscriptWord],
    *,
    duration_ms: int,
) -> SubtitleTimeline:
    if duration_ms < 0:
        raise SubtitleBuildError("项目音频时长不能为负数")
    if not words:
        raise SubtitleBuildError("缺少词级时间戳")

    ordered_pages = sorted(pages, key=lambda page: page.page_order)
    if not ordered_pages:
        raise SubtitleBuildError("缺少字幕页面时间轴")
    _validate_pages(ordered_pages, duration_ms)

    fragments: list[_Fragment] = []
    previous_start = -1
    previous_end = -1
    for index, word in enumerate(words):
        if word.end_ms <= word.start_ms:
            raise SubtitleBuildError("词级时间戳必须递增")
        if word.start_ms < previous_start or word.end_ms < previous_end:
            raise SubtitleBuildError("词级时间戳逆序")
        if word.start_ms < previous_end:
            raise SubtitleBuildError("词级时间戳重叠")
        if word.start_ms < 0 or word.end_ms > duration_ms:
            raise SubtitleBuildError("词级时间戳超出项目音频时长")
        previous_start = word.start_ms
        previous_end = word.end_ms
        for page in ordered_pages:
            start_ms = max(word.start_ms, page.start_ms)
            end_ms = min(word.end_ms, page.end_ms)
            if start_ms < end_ms:
                fragments.append(
                    _Fragment(
                        page=page,
                        word_index=index,
                        text=word.text,
                        start_ms=start_ms,
                        end_ms=end_ms,
                        clipped=start_ms != word.start_ms or end_ms != word.end_ms,
                    )
                )

    if not fragments:
        raise SubtitleBuildError("词级时间戳未落入任何页面")

    cues: list[SubtitleCue] = []
    current: list[_Fragment] = []
    for fragment in fragments:
        if current and not _can_join(current[-1], fragment):
            cues.append(_make_cue(current))
            current = []
        current.append(fragment)
    if current:
        cues.append(_make_cue(current))

    for left, right in zip(cues, cues[1:], strict=False):
        if left.end_ms > right.start_ms:
            raise SubtitleBuildError("生成的字幕时间轴存在重叠")

    return SubtitleTimeline(duration_ms=duration_ms, cues=cues)


def build_heygen_word_timestamps(
    pages: list[SubtitlePageRange], narration_by_page: dict[UUID, str]
) -> list[TranscriptWord]:
    words: list[TranscriptWord] = []
    for page in sorted(pages, key=lambda item: item.page_order):
        tokens = _sentence_tokens(narration_by_page.get(page.page_id, ""))
        if not tokens:
            raise SubtitleBuildError(f"第{page.page_order}页缺少可用于字幕的旁白文本")
        weight_total = sum(len(token) for token in tokens)
        previous_end = page.start_ms
        for index, token in enumerate(tokens):
            if index == len(tokens) - 1:
                end_ms = page.end_ms
            else:
                consumed = sum(len(item) for item in tokens[: index + 1])
                end_ms = page.start_ms + round(
                    (page.end_ms - page.start_ms) * consumed / weight_total
                )
            if end_ms <= previous_end:
                raise SubtitleBuildError(f"第{page.page_order}页音频时长不足以生成字幕时间轴")
            words.append(
                TranscriptWord(
                    text=token,
                    start_ms=previous_end,
                    end_ms=end_ms,
                    confidence=0.75,
                )
            )
            previous_end = end_ms
    return words


def format_srt(timeline: SubtitleTimeline) -> str:
    blocks = []
    for index, cue in enumerate(timeline.cues, start=1):
        blocks.append(
            "\n".join(
                [
                    str(index),
                    f"{_format_timestamp(cue.start_ms)} --> {_format_timestamp(cue.end_ms)}",
                    cue.text,
                ]
            )
        )
    return "\n\n".join(blocks) + ("\n" if blocks else "")


def _validate_pages(pages: list[SubtitlePageRange], duration_ms: int) -> None:
    previous_end = 0
    for page in pages:
        if page.start_ms < previous_end:
            raise SubtitleBuildError("字幕页面时间轴存在重叠")
        if page.end_ms > duration_ms:
            raise SubtitleBuildError("字幕页面时间轴超出项目音频时长")
        previous_end = page.end_ms


def _can_join(left: _Fragment, right: _Fragment) -> bool:
    return (
        left.page.page_id == right.page.page_id
        and not left.clipped
        and not right.clipped
        and not left.text.endswith(("。", "！", "？", "；", ";", "，", ",", "、", "：", ":"))
        and right.start_ms - left.end_ms <= 600
        and len(left.text) + len(right.text) <= 42
    )


def _sentence_tokens(text: str) -> list[str]:
    compact = re.sub(r"\s+", "", text)
    return [
        token
        for token in re.findall(r"[^。！？；;，,、：:]+[。！？；;，,、：:]?", compact)
        if token
    ]


def _make_cue(fragments: list[_Fragment]) -> SubtitleCue:
    page = fragments[0].page
    start_ms = fragments[0].start_ms
    end_ms = max(fragment.end_ms for fragment in fragments)
    text = "".join(fragment.text for fragment in fragments)
    indexes = [fragment.word_index for fragment in fragments]
    cue_id = uuid5(
        NAMESPACE_URL,
        f"subtitle:{page.page_id}:{start_ms}:{end_ms}:{text}:{','.join(map(str, indexes))}",
    )
    return SubtitleCue(
        id=cue_id,
        page_id=page.page_id,
        page_order=page.page_order,
        start_ms=start_ms,
        end_ms=end_ms,
        text=text,
        source_word_indexes=indexes,
    )


def _format_timestamp(milliseconds: int) -> str:
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, millis = divmod(remainder, 1_000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"


def _atomic_write(path: Path, content: bytes) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_bytes(content)
    os.replace(temporary, path)
