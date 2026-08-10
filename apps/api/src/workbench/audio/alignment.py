from __future__ import annotations

import re
import wave
from dataclasses import dataclass
from difflib import SequenceMatcher
from math import ceil
from pathlib import Path
from uuid import UUID, uuid4

from workbench.audio.models import Transcript
from workbench.domain.audio import (
    AudioTimeline,
    AudioTimelineBoundary,
    AudioTimelineSegment,
)


class BoundaryConflict(RuntimeError):
    pass


class BoundaryRejected(ValueError):
    pass


@dataclass(frozen=True)
class PageNarration:
    page_id: UUID
    text: str


@dataclass(frozen=True)
class PageWav:
    page_id: UUID
    path: Path
    start_ms: int
    end_ms: int
    duration_ms: int


def align_pages(
    transcript: Transcript,
    confirmed_narrations: list[PageNarration],
    *,
    silence_intervals_ms: list[tuple[int, int]] | None = None,
    duration_ms: int | None = None,
    min_page_ms: int = 300,
) -> AudioTimeline:
    if not confirmed_narrations:
        raise ValueError("至少需要一页确认旁白")
    if len(transcript.words) < len(confirmed_narrations):
        raise ValueError("转写词数不足以为每页建立有效片段")
    total_duration = duration_ms or (transcript.words[-1].end_ms if transcript.words else 0)
    if total_duration < min_page_ms * len(confirmed_narrations):
        raise ValueError("录音总时长不足以满足最短页时长")
    cuts = _dynamic_programming_cuts(transcript, confirmed_narrations, silence_intervals_ms or [])
    times = [_boundary_time(transcript, cut, silence_intervals_ms or []) for cut in cuts]
    times = _clamp_times(times, total_duration, min_page_ms)
    boundaries = [AudioTimelineBoundary(id=uuid4(), time_ms=value) for value in times]
    return AudioTimeline(
        id=uuid4(),
        duration_ms=total_duration,
        min_page_ms=min_page_ms,
        boundaries=boundaries,
        segments=_segments(confirmed_narrations, times, total_duration),
    )


def update_boundary(
    timeline: AudioTimeline, boundary_id: UUID, time_ms: int, version: int
) -> AudioTimeline:
    if version != timeline.version:
        raise BoundaryConflict("时间轴已在另一个窗口更新")
    index = next(
        (position for position, item in enumerate(timeline.boundaries) if item.id == boundary_id),
        None,
    )
    if index is None:
        raise KeyError(boundary_id)
    lower = (
        timeline.min_page_ms
        if index == 0
        else timeline.boundaries[index - 1].time_ms + timeline.min_page_ms
    )
    upper = (
        timeline.duration_ms - timeline.min_page_ms
        if index == len(timeline.boundaries) - 1
        else timeline.boundaries[index + 1].time_ms - timeline.min_page_ms
    )
    if not lower <= time_ms <= upper:
        raise BoundaryRejected("分页线越序或导致页面音频短于最小时长")
    boundaries = [
        item.model_copy(update={"time_ms": time_ms}) if item.id == boundary_id else item
        for item in timeline.boundaries
    ]
    page_ids = [segment.page_id for segment in timeline.segments]
    narrations = [PageNarration(page_id=value, text="") for value in page_ids]
    times = [item.time_ms for item in boundaries]
    return timeline.model_copy(
        update={
            "version": timeline.version + 1,
            "boundaries": boundaries,
            "segments": _segments(narrations, times, timeline.duration_ms),
        }
    )


def export_page_wavs(audio: Path, timeline: AudioTimeline, output_dir: Path) -> list[PageWav]:
    output_dir.mkdir(parents=True, exist_ok=True)
    with wave.open(str(audio), "rb") as source:
        parameters = source.getparams()
        if parameters.nchannels != 1 or parameters.sampwidth != 2:
            raise ValueError("分页导出要求 16-bit 单声道 WAV")
        frames = source.readframes(parameters.nframes)
    frame_size = parameters.nchannels * parameters.sampwidth
    assets: list[PageWav] = []
    for order, segment in enumerate(timeline.segments, start=1):
        start_frame = round(segment.start_ms * parameters.framerate / 1000)
        end_frame = round(segment.end_ms * parameters.framerate / 1000)
        target = output_dir / f"page-{order:03d}.wav"
        with wave.open(str(target), "wb") as output:
            output.setparams(parameters)
            output.writeframes(frames[start_frame * frame_size : end_frame * frame_size])
        actual_duration = round((end_frame - start_frame) * 1000 / parameters.framerate)
        assets.append(
            PageWav(
                page_id=segment.page_id,
                path=target,
                start_ms=segment.start_ms,
                end_ms=segment.end_ms,
                duration_ms=actual_duration,
            )
        )
    return assets


def _dynamic_programming_cuts(
    transcript: Transcript,
    narrations: list[PageNarration],
    silences: list[tuple[int, int]],
) -> list[int]:
    word_count = len(transcript.words)
    page_count = len(narrations)
    narration_lengths = [max(1, len(_normalize(item.text))) for item in narrations]
    total_narration_length = sum(narration_lengths)
    average_words_per_page = word_count / page_count
    search_radius = max(4, ceil(average_words_per_page * 0.35))
    costs: dict[tuple[int, int], tuple[float, list[int]]] = {(0, 0): (0.0, [])}
    for page_index in range(page_count):
        remaining_pages = page_count - page_index - 1
        maximum_end = word_count - remaining_pages
        if remaining_pages == 0:
            candidate_ends = [word_count]
        else:
            completed_ratio = sum(narration_lengths[: page_index + 1]) / total_narration_length
            expected_end = round(word_count * completed_ratio)
            lower = max(page_index + 1, expected_end - search_radius)
            upper = min(maximum_end, expected_end + search_radius)
            candidate_ends = list(range(lower, upper + 1))
        next_costs: dict[tuple[int, int], tuple[float, list[int]]] = {}
        for (_, start), (cost, cuts) in costs.items():
            for end in candidate_ends:
                if end <= start:
                    continue
                expected = _normalize(narrations[page_index].text)
                actual = _normalize("".join(word.text for word in transcript.words[start:end]))
                mismatch = 1 - SequenceMatcher(None, expected, actual, autojunk=False).ratio()
                silence_bonus = 0.0
                if end < word_count and _silence_near_cut(transcript, end, silences):
                    silence_bonus = 0.08
                candidate = (cost + mismatch - silence_bonus, [*cuts, end])
                key = (page_index + 1, end)
                if key not in next_costs or candidate[0] < next_costs[key][0]:
                    next_costs[key] = candidate
        costs = next_costs
    result = costs.get((page_count, word_count))
    if result is None:
        raise ValueError("无法建立页面与录音的单调对齐")
    return result[1][:-1]


def _boundary_time(transcript: Transcript, cut: int, silences: list[tuple[int, int]]) -> int:
    left = transcript.words[cut - 1].end_ms
    right = transcript.words[cut].start_ms
    candidates = [
        (start, end) for start, end in silences if end >= left - 200 and start <= right + 200
    ]
    if candidates:
        start, end = max(candidates, key=lambda item: item[1] - item[0])
        return round((start + end) / 2)
    return round((left + right) / 2)


def _silence_near_cut(transcript: Transcript, cut: int, silences: list[tuple[int, int]]) -> bool:
    left = transcript.words[cut - 1].end_ms
    right = transcript.words[cut].start_ms
    return any(end >= left - 200 and start <= right + 200 for start, end in silences)


def _clamp_times(times: list[int], duration_ms: int, minimum: int) -> list[int]:
    result: list[int] = []
    for index, value in enumerate(times):
        lower = minimum if index == 0 else result[-1] + minimum
        remaining = len(times) - index
        upper = duration_ms - remaining * minimum
        result.append(min(max(value, lower), upper))
    return result


def _segments(
    narrations: list[PageNarration], times: list[int], duration_ms: int
) -> list[AudioTimelineSegment]:
    edges = [0, *times, duration_ms]
    return [
        AudioTimelineSegment(
            page_id=narration.page_id,
            start_ms=edges[index],
            end_ms=edges[index + 1],
        )
        for index, narration in enumerate(narrations)
    ]


def _normalize(value: str) -> str:
    return "".join(re.findall(r"[a-z0-9\u4e00-\u9fff]", value.casefold()))
