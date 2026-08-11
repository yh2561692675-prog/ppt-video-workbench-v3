from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from workbench.timeline.production import (
    ClipKind,
    ProductionTimeline,
    TimelineClip,
    TimelineCommand,
    TimelineCommandBatch,
    TimelineCompiler,
    TimelineEditor,
    TimelineError,
    TimelineTrack,
)


def _timeline() -> tuple[ProductionTimeline, TimelineTrack, TimelineTrack]:
    project_id = uuid4()
    slide_track = TimelineTrack(kind=ClipKind.SLIDE, name="Slides", order=0)
    narration_track = TimelineTrack(kind=ClipKind.NARRATION, name="Narration", order=1)
    slide_track.clips.append(
        TimelineClip(
            track_id=slide_track.id,
            kind=ClipKind.SLIDE,
            start_us=0,
            duration_us=2_000_000,
            source_ref="slides/page-1.png",
        )
    )
    narration_track.clips.append(
        TimelineClip(
            track_id=narration_track.id,
            kind=ClipKind.NARRATION,
            start_us=0,
            duration_us=2_000_000,
            source_ref="audio/01.wav",
        )
    )
    return (
        ProductionTimeline(
            project_id=project_id,
            duration_us=3_000_000,
            tracks=[slide_track, narration_track],
            input_fingerprint="inputs-v1",
        ),
        slide_track,
        narration_track,
    )


def test_editor_uses_optimistic_revision_and_compiler_is_deterministic_per_clip() -> None:
    timeline, slide_track, narration_track = _timeline()
    editor = TimelineEditor(timeline)
    command = TimelineCommand(
        expected_revision=1,
        kind="move_clip",
        payload={"clip_id": str(slide_track.clips[0].id), "start_us": 100_000},
    )
    updated = editor.apply(command)

    assert updated.revision == 2
    assert updated.content_hash != timeline.content_hash
    assert editor.apply(command) == updated

    with pytest.raises(TimelineError, match="revision"):
        editor.apply(
            TimelineCommand(
                expected_revision=1,
                kind="set_transition",
                payload={"clip_id": str(slide_track.clips[0].id), "enabled": True},
            )
        )

    graph = TimelineCompiler().compile(updated)
    assert len(graph.nodes) == 2
    assert {node.source_ref for node in graph.nodes} == {"slides/page-1.png", "audio/01.wav"}
    assert graph.content_hash


def test_compiler_node_ids_and_hash_are_stable() -> None:
    timeline, _, _ = _timeline()

    first = TimelineCompiler().compile(timeline)
    second = TimelineCompiler().compile(timeline)

    assert [node.id for node in first.nodes] == [node.id for node in second.nodes]
    assert first.content_hash == second.content_hash


def test_replaying_same_command_id_is_idempotent() -> None:
    timeline, slide_track, _ = _timeline()
    editor = TimelineEditor(timeline)
    command = TimelineCommand(
        command_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        expected_revision=1,
        kind="set_transition",
        payload={"clip_id": str(slide_track.clips[0].id), "enabled": True},
    )

    first = editor.apply(command)
    replay = editor.apply(command)

    assert replay == first
    assert replay.revision == 2


def test_command_batch_is_atomic_and_advances_revisions() -> None:
    timeline, slide_track, _ = _timeline()
    editor = TimelineEditor(timeline)
    batch = TimelineCommandBatch(
        expected_revision=1,
        commands=[
            TimelineCommand(
                expected_revision=1,
                kind="move_clip",
                payload={"clip_id": str(slide_track.clips[0].id), "start_us": 100_000},
            ),
            TimelineCommand(
                expected_revision=2,
                kind="set_transition",
                payload={"clip_id": str(slide_track.clips[0].id), "enabled": True},
            ),
        ],
    )

    updated = editor.apply_batch(batch)

    assert updated.revision == 3
    assert updated.tracks[0].clips[0].start_us == 100_000
    assert updated.tracks[0].clips[0].payload["transition_overlap"] is True


def test_editor_split_link_and_ripple_shift() -> None:
    timeline, slide_track, narration_track = _timeline()
    editor = TimelineEditor(timeline)
    clip_id = slide_track.clips[0].id

    updated = editor.apply(
        TimelineCommand(
            expected_revision=1,
            kind="split_clip",
            payload={"clip_id": str(clip_id), "split_at_us": 1_000_000},
        )
    )
    assert len(updated.tracks[0].clips) == 2

    clip_ids = [str(clip.id) for clip in updated.tracks[0].clips]
    updated = editor.apply(
        TimelineCommand(
            expected_revision=2,
            kind="link_clips",
            payload={"clip_ids": [clip_ids[0], str(narration_track.clips[0].id)]},
        )
    )
    assert updated.tracks[0].clips[0].link_group_id is not None

    updated = editor.apply(
        TimelineCommand(
            expected_revision=3,
            kind="ripple_shift",
            payload={"track_id": str(narration_track.id), "from_us": 0, "delta_us": 100_000},
        )
    )
    assert updated.tracks[1].clips[0].start_us == 100_000


def test_slide_track_rejects_unmarked_overlap() -> None:
    project_id = uuid4()
    track = TimelineTrack(kind=ClipKind.SLIDE, name="Slides", order=0)
    track.clips = [
        TimelineClip(
            track_id=track.id, kind=ClipKind.SLIDE, start_us=0, duration_us=2, source_ref="a"
        ),
        TimelineClip(
            track_id=track.id, kind=ClipKind.SLIDE, start_us=1, duration_us=2, source_ref="b"
        ),
    ]
    with pytest.raises(ValueError, match="overlap"):
        ProductionTimeline(project_id=project_id, duration_us=3, tracks=[track])
