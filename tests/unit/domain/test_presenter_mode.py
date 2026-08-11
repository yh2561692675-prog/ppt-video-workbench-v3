from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError
from workbench.domain.models import ProjectManifest
from workbench.domain.presenter import (
    PresentationMode,
    PresenterSource,
    PresenterTimelineV1,
    SlideAnchor,
)


def _project_payload() -> dict[str, object]:
    now = datetime.now(UTC)
    return {
        "id": uuid4(),
        "name": "真人讲解测试",
        "project_dir": "真人讲解测试",
        "created_at": now,
        "updated_at": now,
    }


def test_human_mode_requires_presenter_source() -> None:
    with pytest.raises(ValidationError, match="presenter_source"):
        ProjectManifest(**_project_payload(), presentation_mode="human_presenter")


def test_legacy_manifest_defaults_to_ai_mode() -> None:
    project = ProjectManifest(**_project_payload())

    assert project.presentation_mode is PresentationMode.AI_NARRATION
    assert project.presenter_timeline is None


def test_anchor_ranges_must_be_monotonic_and_inside_media() -> None:
    source = PresenterSource(
        id=uuid4(),
        relative_path="presenter/source.mp4",
        sha256="a" * 64,
        duration_ms=10_000,
    )

    with pytest.raises(ValidationError, match="overlap"):
        PresenterTimelineV1(
            source_id=source.id,
            source_version=source.sha256,
            duration_ms=source.duration_ms,
            anchors=[
                SlideAnchor(
                    page_id=uuid4(),
                    start_ms=0,
                    end_ms=6_000,
                    sentence_ids=["sentence-1"],
                    confidence=0.95,
                    status="auto",
                ),
                SlideAnchor(
                    page_id=uuid4(),
                    start_ms=5_000,
                    end_ms=9_000,
                    sentence_ids=["sentence-2"],
                    confidence=0.9,
                    status="auto",
                ),
            ],
        )


def test_manual_lock_keeps_source_revision() -> None:
    with pytest.raises(ValidationError, match="source_revision"):
        SlideAnchor(
            page_id=uuid4(),
            start_ms=0,
            end_ms=1_000,
            sentence_ids=["sentence-1"],
            confidence=0.95,
            status="confirmed",
            manual_lock=True,
        )
