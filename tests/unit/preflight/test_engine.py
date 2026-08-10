from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from workbench.domain.enums import NodeStatus
from workbench.domain.extraction import PageExtraction, TextSpan
from workbench.domain.models import NarrationRecord, PageRecord, ProjectManifest
from workbench.preflight.engine import PreflightEngine


def _project(tmp_path: Path, *, ready: bool = False) -> ProjectManifest:
    project_id = uuid4()
    project_dir = tmp_path / "预检项目"
    project_dir.mkdir()
    (project_dir / "09_日志").mkdir()
    now = datetime.now(UTC)
    page_id = uuid4()
    revision_id = uuid4()
    preview = project_dir / "02_页面预览" / "page-0001.png"
    if ready:
        preview.parent.mkdir(parents=True)
        preview.write_bytes(b"png fixture")
    return ProjectManifest(
        id=project_id,
        name="预检项目",
        project_dir=project_dir.name,
        created_at=now,
        updated_at=now,
        pages=[
            PageRecord(
                id=page_id,
                order=1,
                title="第一页",
                narration=(
                    NarrationRecord(
                        id=uuid4(),
                        revision_id=revision_id,
                        confirmed_revision_id=revision_id if ready else None,
                        text="第一页旁白" if ready else "",
                        status=NodeStatus.COMPLETED if ready else NodeStatus.NOT_STARTED,
                    )
                    if ready
                    else None
                ),
            )
        ],
        page_extractions=[
            PageExtraction(
                id=uuid4(),
                order=1,
                text="页面文字",
                spans=[TextSpan(text="低置信度", bbox=(0, 0, 100, 40), confidence=0.2)],
                preview_path=preview,
                width=1920 if ready else None,
                height=1080 if ready else None,
                needs_confirmation=not ready,
                extraction_method="ocr",
                source_ref="fixture",
            )
        ],
    )


def test_preflight_returns_structured_issues_for_material_content_audio_and_video(
    tmp_path: Path,
) -> None:
    report = PreflightEngine(tmp_path, runtime_probe=lambda: {}).run_preflight(_project(tmp_path))

    assert report.allowed is False
    assert report.issues
    assert {
        "page_preview_missing",
        "ocr_needs_confirmation",
        "narration_missing",
        "audio_missing",
        "subtitle_missing",
        "runtime_probe_unavailable",
    }.issubset({issue.code for issue in report.issues})
    for issue in report.issues:
        assert issue.issue_id
        assert issue.code
        assert issue.message
        assert issue.action
        assert issue.fingerprint
        assert issue.level.value in {"blocking", "confirmation", "required_warning", "info"}
        assert issue.location is not None
    assert report.snapshot_path is not None


def test_preflight_reuses_unchanged_checks_and_rechecks_changed_content(tmp_path: Path) -> None:
    engine = PreflightEngine(tmp_path, runtime_probe=lambda: {"python": "3.12"})
    initial = _project(tmp_path, ready=True)
    first = engine.run_preflight(initial)
    second = engine.run_preflight(initial.model_copy(deep=True), previous=first)

    assert set(second.reused_checks) == set(first.check_fingerprints) - {"resources"}
    assert second.executed_checks == ["resources"]
    assert second.issues == first.issues

    changed = initial.model_copy(deep=True)
    changed.pages[0].narration = changed.pages[0].narration.model_copy(
        update={"text": "修改后的旁白"}
    )
    third = engine.run_preflight(changed, previous=second)
    assert "content" in third.executed_checks
    assert "content" not in third.reused_checks


def test_material_preflight_resolves_persisted_relative_preview_path(tmp_path: Path) -> None:
    project = _project(tmp_path, ready=True)
    relative_preview = Path("02_页面预览/page-0001.png")
    project.page_extractions[0] = project.page_extractions[0].model_copy(
        update={"preview_path": relative_preview}
    )

    report = PreflightEngine(tmp_path, runtime_probe=lambda: {"python": "3.12"}).run_preflight(
        project,
        scope={"materials"},
    )

    assert "page_preview_missing" not in {issue.code for issue in report.issues}


def test_issue_id_is_stable_for_same_input_and_changes_after_input_change(tmp_path: Path) -> None:
    engine = PreflightEngine(tmp_path, runtime_probe=lambda: {})
    initial = _project(tmp_path)
    first = engine.run_preflight(initial)
    same = engine.run_preflight(initial.model_copy(deep=True), previous=first)

    first_ids = {issue.code: issue.issue_id for issue in first.issues}
    same_ids = {issue.code: issue.issue_id for issue in same.issues}
    assert same_ids == first_ids

    changed = initial.model_copy(deep=True)
    changed.pages[0].title = "标题发生变化"
    changed_report = engine.run_preflight(changed, previous=same)
    assert {
        issue.issue_id for issue in changed_report.issues if issue.code == "narration_missing"
    } != {first_ids["narration_missing"]}


def test_confirmation_level_issue_does_not_allow_render_until_confirmed(tmp_path: Path) -> None:
    report = PreflightEngine(tmp_path, runtime_probe=lambda: {}).run_preflight(_project(tmp_path))

    confirmation_issues = [
        issue
        for issue in report.issues
        if issue.level.value in {"confirmation", "required_warning"}
    ]
    assert confirmation_issues
    assert report.allowed is False
    confirmed = report.model_copy(
        update={
            "issues": [
                issue.model_copy(update={"confirmed": True})
                if issue in confirmation_issues
                else issue
                for issue in report.issues
            ]
        }
    )
    assert confirmed.allowed is False
