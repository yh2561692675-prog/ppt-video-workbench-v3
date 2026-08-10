from uuid import UUID

import pytest
from workbench.audio.models import TranscriptWord
from workbench.subtitles.models import SubtitleBuildError, SubtitlePageRange
from workbench.subtitles.service import (
    build_heygen_word_timestamps,
    build_subtitle_timeline,
    format_srt,
)


def _page(order: int, start_ms: int, end_ms: int) -> SubtitlePageRange:
    return SubtitlePageRange(
        page_id=UUID(int=order),
        page_order=order,
        start_ms=start_ms,
        end_ms=end_ms,
    )


def _word(text: str, start_ms: int, end_ms: int, confidence: float = 0.99) -> TranscriptWord:
    return TranscriptWord(text=text, start_ms=start_ms, end_ms=end_ms, confidence=confidence)


def test_groups_words_by_page_and_preserves_chinese_punctuation() -> None:
    pages = [_page(1, 0, 1_200), _page(2, 1_200, 2_400)]
    words = [
        _word("机械", 100, 360),
        _word("设计，", 360, 640),
        _word("连接", 1_300, 1_540),
        _word("产业。", 1_540, 1_820),
    ]

    timeline = build_subtitle_timeline(pages, words, duration_ms=2_400)

    assert [(cue.page_order, cue.start_ms, cue.end_ms, cue.text) for cue in timeline.cues] == [
        (1, 100, 640, "机械设计，"),
        (2, 1_300, 1_820, "连接产业。"),
    ]
    assert timeline.cues[0].source_word_indexes == [0, 1]


def test_clips_a_word_to_the_page_boundary_without_overlapping_adjacent_page() -> None:
    pages = [_page(1, 0, 1_000), _page(2, 1_000, 2_000)]
    words = [_word("跨页", 900, 1_100), _word("内容。", 1_100, 1_300)]

    timeline = build_subtitle_timeline(pages, words, duration_ms=2_000)

    assert [(cue.page_order, cue.start_ms, cue.end_ms, cue.text) for cue in timeline.cues] == [
        (1, 900, 1_000, "跨页"),
        (2, 1_000, 1_100, "跨页"),
        (2, 1_100, 1_300, "内容。"),
    ]
    assert all(
        left.end_ms <= right.start_ms
        for left, right in zip(timeline.cues, timeline.cues[1:], strict=False)
    )


def test_srt_uses_standard_millisecond_timestamp_format() -> None:
    pages = [_page(1, 0, 2_345)]
    timeline = build_subtitle_timeline(
        pages,
        [_word("第", 1_234, 2_000), _word("一页。", 2_000, 2_345)],
        duration_ms=2_345,
    )

    srt = format_srt(timeline)

    assert "1\n00:00:01,234 --> 00:00:02,345\n第一页。" in srt
    assert "00:00:02.000" not in srt


def test_rejects_word_timestamps_outside_project_duration() -> None:
    with pytest.raises(SubtitleBuildError, match="超出项目音频时长"):
        build_subtitle_timeline(
            [_page(1, 0, 1_000)],
            [_word("越界", 900, 1_100)],
            duration_ms=1_000,
        )


def test_rejects_reverse_or_missing_word_timestamps() -> None:
    pages = [_page(1, 0, 2_000)]

    with pytest.raises(SubtitleBuildError, match="时间戳逆序"):
        build_subtitle_timeline(
            pages,
            [_word("后", 800, 900), _word("前", 700, 750)],
            duration_ms=2_000,
        )

    with pytest.raises(SubtitleBuildError, match="缺少词级时间戳"):
        build_subtitle_timeline(pages, [], duration_ms=2_000)


def test_rejects_overlapping_word_intervals_before_emitting_cues() -> None:
    with pytest.raises(SubtitleBuildError, match="时间戳重叠"):
        build_subtitle_timeline(
            [_page(1, 0, 2_000)],
            [_word("前半句", 100, 900), _word("后半句", 800, 1_300)],
            duration_ms=2_000,
        )


def test_builds_deterministic_word_timestamps_from_heygen_page_audio() -> None:
    pages = [_page(1, 0, 1_000), _page(2, 1_000, 2_500)]

    words = build_heygen_word_timestamps(
        pages,
        {
            pages[0].page_id: "欢迎来到第一部分。",
            pages[1].page_id: "第二页内容，继续说明。",
        },
    )

    assert [(word.text, word.start_ms, word.end_ms) for word in words] == [
        ("欢迎来到第一部分。", 0, 1_000),
        ("第二页内容，", 1_000, 1_818),
        ("继续说明。", 1_818, 2_500),
    ]
    assert all(left.end_ms <= right.start_ms for left, right in zip(words, words[1:], strict=False))
