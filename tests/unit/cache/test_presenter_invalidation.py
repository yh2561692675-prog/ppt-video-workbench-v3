import pytest
from workbench.cache.dependency_graph import invalidate_presenter


@pytest.mark.parametrize(
    ("event", "rebuild"),
    [
        ("presenter_style_changed", {"segments", "final"}),
        ("slide_text_changed", {"match", "anchors", "cues", "segments", "final"}),
        (
            "source_video_changed",
            {"transcript", "match", "anchors", "cues", "segments", "final"},
        ),
    ],
)
def test_presenter_invalidation_is_precise_and_preserves_manual_locks(
    event: str, rebuild: set[str]
) -> None:
    plan = invalidate_presenter(event)
    assert set(plan.rebuild) == rebuild
    assert plan.preserve_manual_locks is True


def test_unknown_presenter_event_is_rejected() -> None:
    with pytest.raises(ValueError, match="unsupported presenter invalidation"):
        invalidate_presenter("unknown")
