from __future__ import annotations

from effects.rhythm import build_rhythm

THREE_CUES = [
    {"id": "cue-1", "start_ms": 500, "end_ms": 1400, "kind": "content"},
    {"id": "cue-2", "start_ms": 1800, "end_ms": 2600, "kind": "content"},
    {"id": "cue-3", "start_ms": 3000, "end_ms": 3900, "kind": "conclusion"},
]


def test_short_page_drops_decoration_before_reading_time() -> None:
    schedule = build_rhythm(5000, THREE_CUES, "standard")

    assert schedule.minimum_reading_ms >= 3000
    assert schedule.decorative_events == ()
    assert schedule.segments[2].name == "content"


def test_schedule_contains_five_monotonic_page_segments() -> None:
    schedule = build_rhythm(12000, THREE_CUES, "standard")

    assert [segment.name for segment in schedule.segments] == [
        "establish",
        "title",
        "content",
        "conclusion",
        "exit",
    ]
    assert all(
        left.end_ms <= right.start_ms
        for left, right in zip(schedule.segments, schedule.segments[1:], strict=False)
    )
    assert schedule.segments[-1].end_ms == 12000


def test_overlapping_cues_are_clipped_to_a_monotonic_schedule() -> None:
    schedule = build_rhythm(
        25000,
        [
            {"id": "a", "start_ms": 1000, "end_ms": 4000},
            {"id": "b", "start_ms": 3500, "end_ms": 7000},
        ],
        "compact",
    )

    assert [(cue.start_ms, cue.end_ms) for cue in schedule.cues] == [
        (1000, 4000),
        (4000, 7000),
    ]


def test_manual_lock_is_preserved_in_schedule() -> None:
    schedule = build_rhythm(3000, [], "enhanced", manual_lock=True)

    assert schedule.manual_lock is True
    assert schedule.minimum_reading_ms == 3000
    assert schedule.decorative_events == ()
