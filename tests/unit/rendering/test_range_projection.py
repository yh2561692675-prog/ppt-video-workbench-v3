from __future__ import annotations

from uuid import uuid4

from workbench.cache.contracts import CacheDependency, CacheDomain
from workbench.rendering.models import (
    AudioMixClip,
    AudioMixPlan,
    GraphCanvas,
    RenderGraphV2,
    RenderNodeV2,
    SubtitleCue,
    SubtitleRenderPlan,
    SubtitleWord,
    TransitionEdge,
)
from workbench.rendering.range_projection import project_render_range


def test_range_projection_rebases_visual_audio_transition_and_subtitle_time() -> None:
    first = RenderNodeV2(
        kind="slide",
        start_us=0,
        end_us=3_000_000,
        source_ref="slide-1.png",
        source_in_us=100_000,
    )
    second = RenderNodeV2(
        kind="slide",
        start_us=2_500_000,
        end_us=5_000_000,
        source_ref="slide-2.png",
    )
    graph = RenderGraphV2(
        project_id=uuid4(),
        timeline_revision=1,
        duration_us=5_000_000,
        canvas=GraphCanvas(width=1920, height=1080, fps=30, duration_us=5_000_000),
        nodes=[first, second],
        transitions=[
            TransitionEdge(
                from_node_id=first.id,
                to_node_id=second.id,
                kind="dissolve",
                start_us=2_500_000,
                end_us=3_000_000,
            )
        ],
        audio=AudioMixPlan(
            clips=[
                AudioMixClip(
                    kind="narration",
                    source_ref="voice.wav",
                    timeline_start_us=500_000,
                    timeline_end_us=4_000_000,
                    source_in_us=200_000,
                )
            ]
        ),
        subtitles=SubtitleRenderPlan(
            render_mode="burn_in",
            cues=[
                SubtitleCue(
                    language="zh",
                    label="zh",
                    start_us=1_500_000,
                    end_us=3_500_000,
                    text="测试字幕",
                    words=[
                        SubtitleWord(text="测试", start_us=1_500_000, end_us=2_500_000),
                        SubtitleWord(text="字幕", start_us=2_500_000, end_us=3_500_000),
                    ],
                )
            ],
        ),
        cache_dependencies=[
            CacheDependency(
                domain=CacheDomain.OVERLAY,
                node_key="overlay:fixture",
                upstream_kind="asset_revision",
                upstream_key="overlay.png",
                upstream_hash="b" * 64,
                start_us=1_000_000,
                end_us=3_000_000,
            )
        ],
        graph_hash="a" * 64,
    )

    projected = project_render_range(graph, 2_000_000, 4_000_000)

    assert projected.duration_us == 2_000_000
    assert [(node.start_us, node.end_us) for node in projected.nodes] == [
        (0, 1_000_000),
        (500_000, 2_000_000),
    ]
    assert projected.nodes[0].source_in_us == 2_100_000
    assert (projected.transitions[0].start_us, projected.transitions[0].end_us) == (
        500_000,
        1_000_000,
    )
    assert projected.audio.clips[0].timeline_start_us == 0
    assert projected.audio.clips[0].source_in_us == 1_700_000
    assert projected.subtitles.cues[0].start_us == 0
    assert projected.subtitles.cues[0].words[0].start_us == 0
    assert projected.source_revisions["projection_start_us"] == "2000000"
    assert projected.cache_dependencies[0].start_us == 0
    assert projected.cache_dependencies[0].end_us == 1_000_000
    assert projected.graph_hash != graph.graph_hash
