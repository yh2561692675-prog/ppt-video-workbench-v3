from __future__ import annotations

from effects.chart import build_chart_sequence


def test_chart_sequence_has_fixed_narrative_order() -> None:
    sequence = build_chart_sequence(
        [{"label": "2024", "value": 10}, {"label": "2025", "value": 16}],
        [{"index": 1, "text": "增长拐点"}],
        "结论：持续增长",
    )

    assert [item.kind for item in sequence] == [
        "baseline",
        "series",
        "key_point",
        "annotation",
        "conclusion",
    ]


def test_chart_without_parseable_data_uses_static_fallback() -> None:
    sequence = build_chart_sequence([], [], "暂无可靠数据")

    assert len(sequence) == 1
    assert sequence[0].kind == "static_fallback"
