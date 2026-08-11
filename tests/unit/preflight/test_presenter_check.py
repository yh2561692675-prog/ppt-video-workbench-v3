from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from workbench.domain.issues import IssueLevel
from workbench.domain.models import PageRecord, ProjectManifest
from workbench.domain.presenter import (
    PresentationMode,
    PresenterSource,
    PresenterTimelineV1,
    SlideAnchor,
)
from workbench.preflight.checks.audio import check_audio
from workbench.preflight.checks.content import check_content
from workbench.preflight.checks.presenter import check_presenter_source


def _project(relative_path: str, warnings: list[str] | None = None) -> ProjectManifest:
    now = datetime.now(UTC)
    source = PresenterSource(
        id=uuid4(),
        relative_path=relative_path,
        sha256="a" * 64,
        duration_ms=10_000,
        probe_snapshot={"warnings": warnings or []},
    )
    return ProjectManifest(
        id=uuid4(),
        name="真人项目",
        project_dir="真人项目",
        created_at=now,
        updated_at=now,
        presentation_mode=PresentationMode.HUMAN_PRESENTER,
        presenter_source=source,
        presenter_timeline=PresenterTimelineV1(
            source_id=source.id,
            source_version=source.sha256,
            duration_ms=source.duration_ms,
        ),
    )


def test_missing_presenter_source_is_blocking(tmp_path: Path) -> None:
    project = _project("01_源文件/presenter/missing.mp4")

    _, issues = check_presenter_source(project, tmp_path)

    assert [(issue.code, issue.level) for issue in issues] == [
        ("PRESENTER_SOURCE_MISSING", IssueLevel.BLOCKING)
    ]


def test_probe_warnings_are_structured_and_non_blocking(tmp_path: Path) -> None:
    source = tmp_path / "01_源文件" / "presenter" / "source.mp4"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"source")
    project = _project(
        "01_源文件/presenter/source.mp4",
        ["PRESENTER_LOW_RESOLUTION", "PRESENTER_VARIABLE_FPS"],
    )

    _, issues = check_presenter_source(project, tmp_path)

    assert {issue.code for issue in issues} == {
        "PRESENTER_LOW_RESOLUTION",
        "PRESENTER_VARIABLE_FPS",
    }
    assert all(issue.level is IssueLevel.REQUIRED_WARNING for issue in issues)
    assert all(not issue.blocking for issue in issues)


def test_blocked_anchor_has_page_time_reason_and_action(tmp_path: Path) -> None:
    source = tmp_path / "01_源文件" / "presenter" / "source.mp4"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"source")
    project = _project("01_源文件/presenter/source.mp4")
    payload = project.model_dump(mode="python")
    payload["presenter_timeline"] = project.presenter_timeline.model_copy(
        update={
            "anchors": [
                SlideAnchor(
                    page_id=uuid4(),
                    start_ms=500,
                    end_ms=1_500,
                    confidence=0.7,
                    status="blocked",
                )
            ]
        }
    )
    project = ProjectManifest.model_validate(payload)

    _, issues = check_presenter_source(project, tmp_path)
    blocked = next(issue for issue in issues if issue.code == "PRESENTER_ANCHOR_BLOCKED")
    assert blocked.location.page_id is not None
    assert blocked.time_range.model_dump() == {"start_ms": 500, "end_ms": 1_500}
    assert blocked.reason == "confidence:0.7000"
    assert blocked.action
    assert blocked.blocking is True


def test_presenter_mode_does_not_require_ai_narration_or_page_audio(tmp_path: Path) -> None:
    source = tmp_path / "01_源文件" / "presenter" / "source.mp4"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"source")
    project = _project("01_源文件/presenter/source.mp4").model_copy(
        update={"pages": [PageRecord(id=uuid4(), order=1, title="第一页")]}
    )

    _, content_issues = check_content(project, tmp_path)
    _, audio_issues = check_audio(project, tmp_path)

    assert "narration_missing" not in {item.code for item in content_issues}
    assert {item.code for item in audio_issues}.isdisjoint(
        {"audio_missing", "timeline_missing", "audio_difference_pending"}
    )
