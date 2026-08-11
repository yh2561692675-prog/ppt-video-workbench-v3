from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

RhythmProfile = Literal["steady", "standard", "compact", "enhanced"]


@dataclass(frozen=True)
class RhythmCue:
    id: str
    start_ms: int
    end_ms: int
    kind: str = "content"


@dataclass(frozen=True)
class RhythmSegment:
    name: Literal["establish", "title", "content", "conclusion", "exit"]
    start_ms: int
    end_ms: int


@dataclass(frozen=True)
class RhythmSchedule:
    duration_ms: int
    profile: RhythmProfile
    segments: tuple[RhythmSegment, ...]
    cues: tuple[RhythmCue, ...]
    minimum_reading_ms: int
    decorative_events: tuple[str, ...]
    manual_lock: bool = False


def build_rhythm(
    duration_ms: int,
    cues: list[RhythmCue | dict[str, object]],
    profile: RhythmProfile,
    *,
    manual_lock: bool = False,
) -> RhythmSchedule:
    if duration_ms <= 0:
        raise ValueError("页面时长必须为正数")

    normalized_cues = _normalize_cues(cues, duration_ms)
    if duration_ms < 5_000:
        segments = _short_segments(duration_ms)
        decorative_events: tuple[str, ...] = ()
        minimum_reading_ms = duration_ms
    else:
        establish_ms = 350
        title_ms = 350
        exit_ms = 350 if duration_ms >= 6_000 else 0
        conclusion_ms = max(1_000, min(2_500, round(duration_ms * 0.1)))
        content_ms = duration_ms - establish_ms - title_ms - conclusion_ms - exit_ms
        if content_ms < 3_000:
            conclusion_ms = max(1_000, duration_ms - establish_ms - title_ms - exit_ms - 3_000)
            content_ms = duration_ms - establish_ms - title_ms - conclusion_ms - exit_ms
        segments = _segments(
            duration_ms,
            establish_ms=establish_ms,
            title_ms=title_ms,
            content_ms=content_ms,
            conclusion_ms=conclusion_ms,
            exit_ms=exit_ms,
        )
        minimum_reading_ms = content_ms
        decorative_events = _decorations(duration_ms, profile)

    return RhythmSchedule(
        duration_ms=duration_ms,
        profile=profile,
        segments=segments,
        cues=normalized_cues,
        minimum_reading_ms=minimum_reading_ms,
        decorative_events=decorative_events,
        manual_lock=manual_lock,
    )


def _short_segments(duration_ms: int) -> tuple[RhythmSegment, ...]:
    return (
        RhythmSegment("establish", 0, 0),
        RhythmSegment("title", 0, 0),
        RhythmSegment("content", 0, duration_ms),
        RhythmSegment("conclusion", duration_ms, duration_ms),
        RhythmSegment("exit", duration_ms, duration_ms),
    )


def _segments(
    duration_ms: int,
    *,
    establish_ms: int,
    title_ms: int,
    content_ms: int,
    conclusion_ms: int,
    exit_ms: int,
) -> tuple[RhythmSegment, ...]:
    establish_end = establish_ms
    title_end = establish_end + title_ms
    content_end = title_end + content_ms
    conclusion_end = content_end + conclusion_ms
    if conclusion_end + exit_ms != duration_ms:
        raise ValueError("节奏段未覆盖完整页面时长")
    return (
        RhythmSegment("establish", 0, establish_end),
        RhythmSegment("title", establish_end, title_end),
        RhythmSegment("content", title_end, content_end),
        RhythmSegment("conclusion", content_end, conclusion_end),
        RhythmSegment("exit", conclusion_end, duration_ms),
    )


def _normalize_cues(
    cues: list[RhythmCue | dict[str, object]], duration_ms: int
) -> tuple[RhythmCue, ...]:
    normalized: list[RhythmCue] = []
    for raw in cues:
        if isinstance(raw, RhythmCue):
            cue = raw
        else:
            cue = RhythmCue(
                id=str(raw.get("id", f"cue-{len(normalized) + 1}")),
                start_ms=int(raw.get("start_ms", 0)),
                end_ms=int(raw.get("end_ms", 0)),
                kind=str(raw.get("kind", "content")),
            )
        start_ms = min(max(cue.start_ms, 0), duration_ms)
        end_ms = min(max(cue.end_ms, start_ms), duration_ms)
        if end_ms <= start_ms:
            continue
        normalized.append(RhythmCue(cue.id, start_ms, end_ms, cue.kind))

    normalized.sort(key=lambda cue: (cue.start_ms, cue.end_ms, cue.id))
    clipped: list[RhythmCue] = []
    for cue in normalized:
        if clipped and cue.start_ms < clipped[-1].end_ms:
            cue = RhythmCue(cue.id, clipped[-1].end_ms, cue.end_ms, cue.kind)
        if cue.end_ms > cue.start_ms:
            clipped.append(cue)
    return tuple(clipped)


def _decorations(duration_ms: int, profile: RhythmProfile) -> tuple[str, ...]:
    if duration_ms < 6_000 or profile == "steady":
        return ()
    if profile == "compact":
        return ("single-focus",)
    if profile == "enhanced":
        return ("background-breath", "single-focus", "semantic-accent")
    return ("background-breath", "single-focus")
