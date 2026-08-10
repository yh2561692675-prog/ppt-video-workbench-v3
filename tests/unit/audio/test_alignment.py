from __future__ import annotations

import wave
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from workbench.audio import alignment as alignment_module
from workbench.audio.alignment import (
    BoundaryConflict,
    BoundaryRejected,
    PageNarration,
    align_pages,
    export_page_wavs,
    update_boundary,
)
from workbench.audio.models import Transcript, TranscriptSegment, TranscriptWord
from workbench.audio.timeline_service import TimelineService
from workbench.domain.audio import AudioImportRecord
from workbench.domain.enums import NodeStatus
from workbench.domain.models import NarrationRecord, PageRecord
from workbench.services.project_service import ProjectService


def _transcript(words: list[tuple[str, int, int]]) -> Transcript:
    records = [
        TranscriptWord(text=text, start_ms=start, end_ms=end, confidence=0.99)
        for text, start, end in words
    ]
    return Transcript(
        segments=[
            TranscriptSegment(
                text="".join(word.text for word in records),
                start_ms=records[0].start_ms,
                end_ms=records[-1].end_ms,
                words=records,
            )
        ],
        words=records,
        detected_language="zh",
        model="small",
        device="cpu",
    )


def test_aligns_pages_and_prefers_nearby_silence() -> None:
    page_one, page_two = uuid4(), uuid4()
    transcript = _transcript(
        [("第一页内容", 0, 900), ("重复句", 950, 1400), ("第二页内容", 2200, 3100)]
    )
    timeline = align_pages(
        transcript,
        [PageNarration(page_one, "第一页内容重复句"), PageNarration(page_two, "第二页内容")],
        silence_intervals_ms=[(1400, 2200)],
        duration_ms=3200,
    )

    assert [segment.page_id for segment in timeline.segments] == [page_one, page_two]
    assert timeline.segments[0].start_ms == 0
    assert timeline.segments[0].end_ms == timeline.segments[1].start_ms
    assert 1400 <= timeline.boundaries[0].time_ms <= 2200
    assert timeline.segments[-1].end_ms == 3200


def test_no_pause_and_cross_page_repeated_phrase_still_produce_ordered_boundaries() -> None:
    pages = [uuid4(), uuid4(), uuid4()]
    transcript = _transcript([("开场重复", 0, 600), ("中段重复", 600, 1200), ("结尾", 1200, 1800)])
    timeline = align_pages(
        transcript,
        [
            PageNarration(pages[0], "开场重复"),
            PageNarration(pages[1], "中段重复"),
            PageNarration(pages[2], "结尾"),
        ],
        duration_ms=1800,
    )
    assert [item.time_ms for item in timeline.boundaries] == sorted(
        item.time_ms for item in timeline.boundaries
    )
    assert all(item.end_ms > item.start_ms for item in timeline.segments)


def test_ten_minute_scale_alignment_uses_bounded_candidate_search(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    matcher_calls = 0

    class CountingMatcher:
        def __init__(self, *_: object, **__: object) -> None:
            nonlocal matcher_calls
            matcher_calls += 1

        def ratio(self) -> float:
            return 0.5

    monkeypatch.setattr(alignment_module, "SequenceMatcher", CountingMatcher)
    words = [(f"词{index}", index * 1_500, (index + 1) * 1_500) for index in range(400)]
    pages = [uuid4() for _ in range(8)]

    timeline = align_pages(
        _transcript(words),
        [PageNarration(page, f"第{index + 1}页旁白") for index, page in enumerate(pages)],
        duration_ms=600_000,
    )

    assert len(timeline.segments) == 8
    assert matcher_calls < 30_000


def test_boundary_updates_enforce_version_order_and_minimum_page_duration() -> None:
    pages = [uuid4(), uuid4(), uuid4()]
    timeline = align_pages(
        _transcript([("一", 0, 1000), ("二", 1000, 2000), ("三", 2000, 3000)]),
        [
            PageNarration(pages[0], "一"),
            PageNarration(pages[1], "二"),
            PageNarration(pages[2], "三"),
        ],
        duration_ms=3000,
        min_page_ms=300,
    )
    boundary = timeline.boundaries[0]
    changed = update_boundary(timeline, boundary.id, 1200, version=1)
    assert changed.version == 2
    assert changed.boundaries[0].time_ms == 1200
    with pytest.raises(BoundaryConflict):
        update_boundary(changed, boundary.id, 1300, version=1)
    with pytest.raises(BoundaryRejected):
        update_boundary(changed, boundary.id, 50, version=2)
    with pytest.raises(BoundaryRejected):
        update_boundary(changed, boundary.id, changed.boundaries[1].time_ms, version=2)


def test_exports_page_wavs_without_overlap_gap_or_duration_drift(tmp_path: Path) -> None:
    audio = tmp_path / "full.wav"
    with wave.open(str(audio), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(16_000)
        handle.writeframes(b"\0\0" * 48_000)
    pages = [uuid4(), uuid4(), uuid4()]
    timeline = align_pages(
        _transcript([("一", 0, 1000), ("二", 1000, 2000), ("三", 2000, 3000)]),
        [
            PageNarration(pages[0], "一"),
            PageNarration(pages[1], "二"),
            PageNarration(pages[2], "三"),
        ],
        duration_ms=3000,
    )

    assets = export_page_wavs(audio, timeline, tmp_path / "pages")

    assert len(assets) == 3
    assert [item.start_ms for item in assets[1:]] == [item.end_ms for item in assets[:-1]]
    assert abs(sum(item.duration_ms for item in assets) - 3000) < 20
    assert all(item.path.exists() for item in assets)


def test_timeline_service_persists_boundaries_and_page_audio(tmp_path: Path) -> None:
    projects = ProjectService(tmp_path / "workspace")
    manifest = projects.create("时间轴项目")
    project_dir = projects.workspace_root / manifest.project_dir
    audio = project_dir / "05_音频" / "full.wav"
    with wave.open(str(audio), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(16_000)
        handle.writeframes(b"\0\0" * 32_000)
    pages = []
    for order, text in enumerate(["第一页", "第二页"], start=1):
        revision = uuid4()
        pages.append(
            PageRecord(
                id=uuid4(),
                order=order,
                narration=NarrationRecord(
                    id=uuid4(),
                    revision_id=revision,
                    text=text,
                    status=NodeStatus.COMPLETED,
                    confirmed_revision_id=revision,
                ),
            )
        )
    transcript = _transcript([("第一页", 0, 900), ("第二页", 1100, 1900)])
    projects.save(
        manifest.model_copy(
            update={
                "pages": pages,
                "transcript": transcript,
                "audio_import": AudioImportRecord(
                    id=uuid4(),
                    original_relative_path="05_音频/full.wav",
                    normalized_relative_path="05_音频/full.wav",
                    duration_ms=2000,
                    sample_rate=16000,
                    channels=1,
                    sha256="a" * 64,
                    peak_dbfs=-20,
                    silence_ratio=0.1,
                    silence_intervals_ms=[(900, 1100)],
                    imported_at=datetime.now(UTC),
                ),
            }
        )
    )

    timeline = TimelineService(projects).build(manifest.id)
    reopened = projects.get(manifest.id)

    assert reopened.audio_timeline == timeline
    assert all(page.audio and page.audio.relative_path for page in reopened.pages)
    assert all(
        (project_dir / page.audio.relative_path).exists() for page in reopened.pages if page.audio
    )
    projects.close()
