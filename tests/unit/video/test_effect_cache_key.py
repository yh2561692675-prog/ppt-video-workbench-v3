from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from workbench.video.models import ProjectVideoProps, VideoPageProps
from workbench.video.render_service import VideoRenderService


def _props(effect_hash: str) -> ProjectVideoProps:
    page = VideoPageProps(
        page_id=uuid4(),
        page_order=1,
        title="page",
        image_path="preview.png",
        audio_path="audio.wav",
        start_ms=0,
        end_ms=1_000,
        effect_plan_hash=effect_hash,
        effect_plan_revision=1,
    )
    return ProjectVideoProps(
        schema_version=2,
        project_id=uuid4(),
        duration_ms=1_000,
        template_version="effect-engine-v2",
        catalog_version="effect-catalog-v2",
        pages=[page],
        subtitles=[],
    )


def test_effect_hash_changes_page_cache_key(tmp_path: Path) -> None:
    renderer = VideoRenderService(tmp_path, renderer=object())
    source = tmp_path / "preview.png"
    source.write_bytes(b"preview")

    first = renderer._cache_key(_props("a" * 64), _props("a" * 64).pages[0], source)
    second = renderer._cache_key(_props("b" * 64), _props("b" * 64).pages[0], source)

    assert first != second
