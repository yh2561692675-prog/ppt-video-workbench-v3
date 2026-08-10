from __future__ import annotations

import pytest


def test_p07_normalizes_audio_metadata_and_builds_page_segments() -> None:
    from workbench.business_modules.p07_audio.runner import build_audio_pipeline

    result = build_audio_pipeline(
        {"duration_ms": 10_000, "sample_rate": 48_000, "channels": 2},
        [{"page_id": "a", "duration_ms": 4_000}, {"page_id": "b", "duration_ms": 6_000}],
    )

    assert result["normalized"]["sample_rate"] == 48_000
    assert result["segments"][1]["start_ms"] == 4_000
    assert result["segments"][1]["end_ms"] == 10_000


def test_p07_rejects_duration_mismatch() -> None:
    from workbench.business_modules.p07_audio.runner import AudioRejected, build_audio_pipeline

    with pytest.raises(AudioRejected):
        build_audio_pipeline({"duration_ms": 1000, "sample_rate": 48000, "channels": 2}, [])
