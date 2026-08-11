from uuid import uuid4

import pytest
from workbench.rendering.models import AffectedRange, GraphCanvas, RenderGraphV2
from workbench.rendering.preview import (
    PreviewRangeError,
    RenderGraphPreviewRequest,
    build_preview_plan,
)


def _graph() -> RenderGraphV2:
    return RenderGraphV2(
        project_id=uuid4(),
        timeline_revision=1,
        duration_us=5_000_000,
        canvas=GraphCanvas(width=1920, height=1080, fps=30),
        affected_ranges=[
            AffectedRange(start_us=1_000_000, end_us=2_000_000, reasons=["transition"]),
            AffectedRange(start_us=3_000_000, end_us=4_000_000, reasons=["subtitle"]),
        ],
        graph_hash="0" * 64,
    )


def test_preview_plan_is_deterministic_and_selects_intersecting_ranges() -> None:
    graph = _graph()
    request = RenderGraphPreviewRequest(
        start_us=1_500_000,
        end_us=3_500_000,
        preset="authoritative",
        runtime_version="test-runtime",
    )

    first = build_preview_plan(graph, request)
    second = build_preview_plan(graph, request)

    assert first == second
    assert len(first.cache_key) == 64
    assert [item.reasons for item in first.affected_ranges] == [["transition"], ["subtitle"]]


@pytest.mark.parametrize(
    ("start_us", "end_us", "message"),
    [
        (2_000_000, 2_000_000, "later than start"),
        (4_000_000, 6_000_000, "exceeds graph duration"),
    ],
)
def test_preview_plan_rejects_invalid_ranges(start_us: int, end_us: int, message: str) -> None:
    with pytest.raises(PreviewRangeError, match=message):
        build_preview_plan(_graph(), RenderGraphPreviewRequest(start_us=start_us, end_us=end_us))
