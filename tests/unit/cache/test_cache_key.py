from __future__ import annotations

from workbench.cache.key import CacheKeyBuilder


def test_cache_key_uses_canonical_json_and_sha256() -> None:
    builder = CacheKeyBuilder()
    first = builder.build(
        "subtitle",
        {
            "source_hash": "source-1",
            "content_version": "content-1",
            "template_version": "tech-board-v1",
            "audio_source": "local",
            "timeline_version": 3,
            "subtitle_style_version": "style-1",
            "nested": {"z": 2, "a": 1},
        },
    )
    reordered = builder.build(
        "subtitle",
        {
            "nested": {"a": 1, "z": 2},
            "subtitle_style_version": "style-1",
            "timeline_version": 3,
            "audio_source": "local",
            "template_version": "tech-board-v1",
            "content_version": "content-1",
            "source_hash": "source-1",
        },
    )

    assert first == reordered
    assert len(first) == 64
    assert builder.build("subtitle", {"items": [1, 2]}) != builder.build(
        "subtitle", {"items": [2, 1]}
    )
    assert first != builder.build("segment", {"source_hash": "source-1"})


def test_cache_key_normalizes_uuid_and_path_like_values() -> None:
    from pathlib import Path
    from uuid import UUID

    builder = CacheKeyBuilder()
    assert builder.build(
        "audio", {"page": UUID("00000000-0000-0000-0000-000000000001"), "path": Path("a.wav")}
    ) == builder.build("audio", {"page": "00000000-0000-0000-0000-000000000001", "path": "a.wav"})
