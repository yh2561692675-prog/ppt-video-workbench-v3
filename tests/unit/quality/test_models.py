from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import ValidationError
from workbench.quality.models import (
    EvidenceRef,
    NormalizedRect,
    PageSpan,
    QualityIssue,
    QualityPolicy,
    QualitySeverity,
)


def test_page_span_rejects_non_positive_duration() -> None:
    with pytest.raises(ValidationError):
        PageSpan(page_id=uuid4(), start_ms=100, end_ms=100)


def test_normalized_rect_rejects_out_of_bounds() -> None:
    with pytest.raises(ValidationError):
        NormalizedRect(x=0.9, y=0, width=0.2, height=0.2)


def test_quality_issue_uses_time_range_scope_when_interval_is_present() -> None:
    issue = QualityIssue(
        code="black_frame",
        severity=QualitySeverity.P1,
        scope="time_range",
        start_ms=100,
        end_ms=700,
        message="黑帧",
        action="重渲染",
    )
    assert issue.scope.value == "time_range"


def test_quality_evidence_rejects_absolute_and_parent_paths() -> None:
    with pytest.raises(ValidationError):
        EvidenceRef(relative_path="C:/outside.png", kind="frame")
    with pytest.raises(ValidationError):
        EvidenceRef(relative_path="evidence/../outside.png", kind="frame")


def test_quality_issue_requires_complete_time_range() -> None:
    with pytest.raises(ValidationError):
        QualityIssue(
            code="drift",
            severity=QualitySeverity.P1,
            scope="time_range",
            start_ms=100,
            message="漂移",
            action="重编译",
        )


def test_quality_policy_presets_are_versioned_and_strict_blocks_p2() -> None:
    strict = QualityPolicy.preset("strict")
    standard = QualityPolicy.preset("standard")
    fast = QualityPolicy.preset("fast")

    assert strict.name == "strict"
    assert strict.p2_blocks is True
    assert strict.max_subtitle_text_length < standard.max_subtitle_text_length
    assert fast.black_frame_min_ms > standard.black_frame_min_ms
    assert fast.p2_blocks is False
