from __future__ import annotations

from pathlib import Path

import pytest
from workbench.content_assist import (
    ContentAssistRepository,
    ContentAssistRequestV1,
    ContentAssistService,
    ContentAssistUnavailable,
)


def test_local_polish_and_segmentation_remain_candidates(tmp_path: Path) -> None:
    service = ContentAssistService(ContentAssistRepository(tmp_path / "assist"))
    polished = service.create(
        ContentAssistRequestV1(kind="polish", source_text="  这 是旁白  ", style="neutral")
    )
    assert polished.status == "candidate"
    assert polished.candidate_text.endswith("。")
    segmented = service.create(
        ContentAssistRequestV1(
            kind="segment", source_text="第一句。第二句，第三句。", max_segment_chars=10
        )
    )
    assert segmented.segments
    assert segmented.status == "candidate"


def test_translation_without_provider_is_explicitly_blocked(tmp_path: Path) -> None:
    service = ContentAssistService(ContentAssistRepository(tmp_path / "assist"))
    candidate = service.create(
        ContentAssistRequestV1(
            kind="translate",
            source_text="你好",
            source_language="zh-CN",
            target_language="en-US",
        )
    )
    assert candidate.status == "needs_provider"
    with pytest.raises(ContentAssistUnavailable):
        service.accept(candidate.candidate_id)


def test_injected_sandbox_translation_requires_explicit_accept(tmp_path: Path) -> None:
    service = ContentAssistService(
        ContentAssistRepository(tmp_path / "assist"),
        translator=lambda text, _source, _target: "hello: " + text,
    )
    candidate = service.create(
        ContentAssistRequestV1(
            kind="translate",
            source_text="你好",
            source_language="zh-CN",
            target_language="en-US",
        )
    )
    assert candidate.status == "candidate"
    accepted = service.accept(candidate.candidate_id)
    assert accepted.status == "accepted"
