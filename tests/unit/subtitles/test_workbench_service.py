from __future__ import annotations

from uuid import uuid4

import pytest
from workbench.subtitles.models import SubtitleCue, SubtitleTimeline
from workbench.subtitles.workbench_models import (
    SubtitleTranslationRequest,
    SubtitleWorkbenchCommand,
)
from workbench.subtitles.workbench_service import (
    SubtitleWorkbenchConflict,
    SubtitleWorkbenchService,
)


def _service(tmp_path):
    project_id = uuid4()
    return (
        project_id,
        SubtitleWorkbenchService(
            tmp_path,
            project_dir_resolver=lambda _: "project",
            legacy_getter=lambda _: SubtitleTimeline(
                duration_ms=5000,
                cues=[
                    SubtitleCue(
                        id=uuid4(),
                        page_id=uuid4(),
                        page_order=1,
                        start_ms=0,
                        end_ms=2500,
                        text="Hello world",
                        source_word_indexes=[0, 1],
                    ),
                    SubtitleCue(
                        id=uuid4(),
                        page_id=uuid4(),
                        page_order=2,
                        start_ms=2500,
                        end_ms=5000,
                        text="Second cue",
                        source_word_indexes=[2, 3],
                    ),
                ],
            ),
        ),
    )


def test_create_edit_split_and_persist(tmp_path):
    project_id, service = _service(tmp_path)
    document = service.get(project_id)
    cue = document.tracks[0].cues[0]

    updated = service.apply(
        project_id,
        SubtitleWorkbenchCommand(
            expected_revision=document.revision,
            kind="update_cue",
            payload={"language": "zh-CN", "cue_id": str(cue.id), "text": "你好世界"},
        ),
    )
    assert updated.revision == 2
    split = service.apply(
        project_id,
        SubtitleWorkbenchCommand(
            expected_revision=updated.revision,
            kind="split_cue",
            payload={"language": "zh-CN", "cue_id": str(cue.id), "split_ms": 1200},
        ),
    )
    assert len(split.tracks[0].cues) == 3
    assert service.revisions(project_id)[-1].content_hash == split.content_hash


def test_idempotency_and_revision_conflict(tmp_path):
    project_id, service = _service(tmp_path)
    document = service.get(project_id)
    cue = document.tracks[0].cues[0]
    command = SubtitleWorkbenchCommand(
        expected_revision=document.revision,
        kind="set_translation",
        payload={"language": "zh-CN", "cue_id": str(cue.id), "translation": "译文"},
    )
    first = service.apply(project_id, command)
    assert service.apply(project_id, command) == first
    with pytest.raises(SubtitleWorkbenchConflict):
        service.apply(
            project_id,
            SubtitleWorkbenchCommand(
                expected_revision=document.revision,
                kind="set_render_mode",
                payload={"render_mode": "burn_in"},
            ),
        )


def test_translation_track_uses_supplied_cues(tmp_path):
    project_id, service = _service(tmp_path)
    document = service.get(project_id)
    primary = document.tracks[0]
    result = service.translate(
        project_id,
        SubtitleTranslationRequest(
            language="en",
            label="English",
            translations={str(primary.cues[0].id): "Hello"},
        ),
    )
    assert result.translated_cue_count == 1
    assert {track.language for track in result.document.tracks} == {"zh-CN", "en"}
