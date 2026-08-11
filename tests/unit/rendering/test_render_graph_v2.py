from __future__ import annotations

from pathlib import Path
from uuid import UUID, uuid4

from workbench.assets.models import AssetKind, AssetRecord, LicenseRecord, LicenseStatus
from workbench.continuity.models import (
    AudioCutMode,
    ContinuityPlan,
    TransitionKind,
    TransitionSpec,
)
from workbench.rendering.asset_resolver import AssetResolver
from workbench.rendering.compiler import RenderGraphCompiler
from workbench.rendering.preflight import GraphPreflight
from workbench.rendering.snapshot_store import RenderGraphSnapshotStore
from workbench.rendering.timebase import (
    duration_to_frames,
    us_range_to_frames,
    us_to_frame_ceil,
    us_to_frame_floor,
)
from workbench.subtitles.workbench_models import (
    SubtitleCueV2,
    SubtitleLanguageTrack,
    SubtitleRenderMode,
    SubtitleStyleTemplate,
    SubtitleWordTiming,
    SubtitleWorkbenchDocument,
)
from workbench.timeline.production import ClipKind, ProductionTimeline, TimelineClip, TimelineTrack


def _timeline() -> tuple[ProductionTimeline, TimelineTrack, TimelineTrack]:
    project_id = uuid4()
    slides = TimelineTrack(kind=ClipKind.SLIDE, name="Slides", order=0)
    narration = TimelineTrack(kind=ClipKind.NARRATION, name="Narration", order=1)
    page_id = uuid4()
    slides.clips.append(
        TimelineClip(
            track_id=slides.id,
            kind=ClipKind.SLIDE,
            start_us=0,
            duration_us=2_000_000,
            source_ref="media/page.png",
            payload={"page_id": str(page_id)},
        )
    )
    narration.clips.append(
        TimelineClip(
            track_id=narration.id,
            kind=ClipKind.NARRATION,
            start_us=0,
            duration_us=2_000_000,
            source_ref="media/narration.wav",
            payload={"page_id": str(page_id)},
        )
    )
    return (
        ProductionTimeline(
            project_id=project_id,
            duration_us=2_000_000,
            tracks=[slides, narration],
            input_fingerprint="fixture",
        ),
        slides,
        narration,
    )


def test_timebase_uses_floor_start_and_ceil_end() -> None:
    assert us_to_frame_floor(33_333, 30) == 0
    assert us_to_frame_ceil(33_334, 30) == 2
    assert us_range_to_frames(33_333, 66_667, 30).duration == 2
    assert duration_to_frames(0, 30) == 1


def test_compiler_is_deterministic_and_compiles_transition_audio_and_subtitles(
    tmp_path: Path,
) -> None:
    timeline, slides, _ = _timeline()
    first_page = UUID(str(slides.clips[0].payload["page_id"]))
    second_page = uuid4()
    slides.clips.append(
        TimelineClip(
            track_id=slides.id,
            kind=ClipKind.SLIDE,
            start_us=2_000_000,
            duration_us=1_000_000,
            source_ref="media/page-2.png",
            payload={"page_id": str(second_page)},
        )
    )
    timeline = timeline.model_copy(update={"duration_us": 3_000_000})
    continuity = ContinuityPlan(
        project_id=timeline.project_id,
        duration_ms=3_000,
        transitions=[
            TransitionSpec(
                from_page_id=first_page,
                to_page_id=second_page,
                kind=TransitionKind.DISSOLVE,
                duration_ms=200,
                audio_mode=AudioCutMode.J_CUT,
                audio_offset_ms=100,
            )
        ],
    )
    subtitles = SubtitleWorkbenchDocument(
        duration_ms=3_000,
        render_mode=SubtitleRenderMode.BOTH,
        default_style=SubtitleStyleTemplate(name="Default"),
        tracks=[
            SubtitleLanguageTrack(
                language="zh-CN",
                label="中文",
                primary=True,
                cues=[
                    SubtitleCueV2(
                        start_ms=100,
                        end_ms=800,
                        text="你好",
                        words=[SubtitleWordTiming(text="你好", start_ms=100, end_ms=400)],
                    )
                ],
            )
        ],
        updated_at="2026-08-11T00:00:00Z",
    )
    graph = RenderGraphCompiler().compile(
        timeline, continuity=continuity, subtitles=subtitles, project_root=tmp_path
    )
    assert graph.schema_version == "2.0"
    assert graph.graph_hash and len(graph.graph_hash) == 64
    assert graph.subtitles.render_mode == "both"
    assert graph.transitions[0].audio_mode == "j_cut"
    assert graph.subtitles.cues[0].words[0].start_us == 100_000
    domains = {dependency.domain.value for dependency in graph.cache_dependencies}
    assert {"video_only", "audio", "transition", "subtitle_soft", "subtitle_burn_in"} <= domains
    assert any(
        dependency.upstream_kind == "compiler"
        and dependency.upstream_key == graph.compiler_version
        for dependency in graph.cache_dependencies
    )
    reasons = {reason for affected in graph.affected_ranges for reason in affected.reasons}
    assert {"audio:j_cut", "subtitle:both", "transition:dissolve"} <= reasons
    assert (
        RenderGraphCompiler()
        .compile(timeline, continuity=continuity, subtitles=subtitles, project_root=tmp_path)
        .graph_hash
        == graph.graph_hash
    )


def test_snapshot_store_and_preflight_block_missing_or_expired_assets(tmp_path: Path) -> None:
    timeline, _, _ = _timeline()
    (tmp_path / "media").mkdir()
    (tmp_path / "media" / "page.png").write_bytes(b"page")
    (tmp_path / "media" / "narration.wav").write_bytes(b"audio")
    graph = RenderGraphCompiler().compile(timeline, project_root=tmp_path)
    store = RenderGraphSnapshotStore(tmp_path)
    store.set_current(timeline.project_id, graph)
    assert store.current(timeline.project_id).graph_hash == graph.graph_hash
    report = GraphPreflight().check(graph, tmp_path, strict_assets=False)
    assert report.allowed

    expired = AssetRecord(
        project_id=timeline.project_id,
        kind=AssetKind.IMAGE,
        content_hash="0" * 64,
        relative_object_path="media/page.png",
        original_name="page.png",
        mime_type="image/png",
        size_bytes=1,
        license=LicenseRecord(status=LicenseStatus.EXPIRED),
    )
    resolved = AssetResolver(tmp_path, [expired]).resolve("media/page.png")
    graph = graph.model_copy(update={"assets": [resolved], "graph_hash": "0" * 64})
    report = GraphPreflight().check(graph, tmp_path, verify_hash=False)
    assert not report.allowed
    assert "ASSET_LICENSE_BLOCKED" in {issue.code for issue in report.issues}
