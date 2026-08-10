from __future__ import annotations

from uuid import uuid4


def test_p08_builds_timeline_and_srt_from_word_timestamps() -> None:
    from workbench.business_modules.p08_subtitle.runner import build_subtitle_payload

    page_id = uuid4()
    payload = build_subtitle_payload(
        [{"page_id": str(page_id), "page_order": 1, "start_ms": 0, "end_ms": 1000}],
        [{"text": "你好", "start_ms": 100, "end_ms": 500, "confidence": 0.98}],
        1000,
    )

    assert payload["timeline"]["cues"][0]["text"] == "你好"
    assert "00:00:00,100 --> 00:00:00,500" in payload["srt"]
