from __future__ import annotations

from uuid import uuid4

from workbench.cache.contracts import CacheDependency
from workbench.rendering.hashing import sha256_json
from workbench.rendering.models import (
    AffectedRange,
    AudioMixClip,
    AudioMixPlan,
    RenderGraphV2,
    RenderNodeV2,
    SubtitleCue,
    SubtitleRenderPlan,
    SubtitleWord,
    TransitionEdge,
)
from workbench.rendering.timebase import us_range_to_frames


class RangeProjectionError(ValueError):
    pass


def project_render_range(graph: RenderGraphV2, start_us: int, end_us: int) -> RenderGraphV2:
    if start_us < 0 or end_us <= start_us:
        raise RangeProjectionError("preview range must satisfy 0 <= start < end")
    if end_us > graph.duration_us:
        raise RangeProjectionError("preview range exceeds graph duration")
    duration_us = end_us - start_us
    nodes = [_project_node(node, start_us, end_us, graph.canvas.fps or 30) for node in graph.nodes]
    selected_nodes = [node for node in nodes if node is not None]
    node_ids = {node.id for node in selected_nodes}
    transitions: list[TransitionEdge] = []
    for edge in graph.transitions:
        if edge.from_node_id not in node_ids or edge.to_node_id not in node_ids:
            continue
        projected_transition = _project_transition(edge, start_us, end_us)
        if projected_transition is not None:
            transitions.append(projected_transition)
    audio_clips: list[AudioMixClip] = []
    for clip in graph.audio.clips:
        projected_audio = _project_audio(clip, start_us, end_us)
        if projected_audio is not None:
            audio_clips.append(projected_audio)
    audio = AudioMixPlan(
        clips=audio_clips,
        ducking=graph.audio.ducking,
        loudness_target_lufs=graph.audio.loudness_target_lufs,
        true_peak_db=graph.audio.true_peak_db,
    )
    subtitle_cues: list[SubtitleCue] = []
    for cue in graph.subtitles.cues:
        projected_cue = _project_cue(cue, start_us, end_us)
        if projected_cue is not None:
            subtitle_cues.append(projected_cue)
    subtitles = graph.subtitles.model_copy(update={"cues": subtitle_cues})
    referenced_asset_ids = {
        node.asset_id for node in selected_nodes if node.asset_id is not None
    } | {clip.asset_id for clip in audio.clips if clip.asset_id is not None}
    affected_ranges: list[AffectedRange] = []
    for item in graph.affected_ranges:
        projected_range = _project_affected(item, start_us, end_us)
        if projected_range is not None:
            affected_ranges.append(projected_range)
    cache_dependencies = [
        projected
        for dependency in graph.cache_dependencies
        if (projected := _project_dependency(dependency, start_us, end_us)) is not None
    ]
    canvas = graph.canvas.model_copy(update={"duration_us": duration_us})
    draft = RenderGraphV2(
        graph_id=uuid4(),
        project_id=graph.project_id,
        timeline_revision=graph.timeline_revision,
        timeline_hash=graph.timeline_hash,
        compiler_version=graph.compiler_version,
        duration_us=duration_us,
        canvas=canvas,
        nodes=selected_nodes,
        transitions=transitions,
        assets=[asset for asset in graph.assets if asset.asset_id in referenced_asset_ids],
        audio=audio,
        subtitles=SubtitleRenderPlan.model_validate(subtitles.model_dump()),
        source_revisions={
            **graph.source_revisions,
            "projection_source_graph_id": str(graph.graph_id),
            "projection_source_graph_hash": graph.graph_hash,
            "projection_start_us": str(start_us),
            "projection_end_us": str(end_us),
        },
        cache_dependencies=cache_dependencies,
        affected_ranges=affected_ranges,
        graph_hash="0" * 64,
    )
    payload = draft.model_dump(mode="json", exclude={"graph_hash", "created_at"})
    return draft.model_copy(update={"graph_hash": sha256_json(payload)})


def _project_node(
    node: RenderNodeV2, start_us: int, end_us: int, fps: int
) -> RenderNodeV2 | None:
    if node.start_us >= end_us or node.end_us <= start_us:
        return None
    clipped_start = max(node.start_us, start_us)
    clipped_end = min(node.end_us, end_us)
    projected_start = clipped_start - start_us
    projected_end = clipped_end - start_us
    frames = us_range_to_frames(projected_start, projected_end, fps)
    return node.model_copy(
        update={
            "start_us": projected_start,
            "end_us": projected_end,
            "start_frame": frames.start,
            "end_frame_exclusive": frames.end,
            "source_in_us": node.source_in_us + max(0, start_us - node.start_us),
        }
    )


def _project_transition(
    edge: TransitionEdge, start_us: int, end_us: int
) -> TransitionEdge | None:
    if edge.start_us == edge.end_us:
        if not start_us <= edge.start_us < end_us:
            return None
        point = edge.start_us - start_us
        return edge.model_copy(update={"start_us": point, "end_us": point, "duration_us": 0})
    if edge.start_us >= end_us or edge.end_us <= start_us:
        return None
    projected_start = max(edge.start_us, start_us) - start_us
    projected_end = min(edge.end_us, end_us) - start_us
    return edge.model_copy(
        update={
            "start_us": projected_start,
            "end_us": projected_end,
            "duration_us": projected_end - projected_start,
        }
    )


def _project_audio(
    clip: AudioMixClip, start_us: int, end_us: int
) -> AudioMixClip | None:
    if clip.timeline_start_us >= end_us or clip.timeline_end_us <= start_us:
        return None
    clipped_start = max(clip.timeline_start_us, start_us)
    clipped_end = min(clip.timeline_end_us, end_us)
    return clip.model_copy(
        update={
            "timeline_start_us": clipped_start - start_us,
            "timeline_end_us": clipped_end - start_us,
            "source_in_us": clip.source_in_us + max(0, start_us - clip.timeline_start_us),
        }
    )


def _project_cue(cue: SubtitleCue, start_us: int, end_us: int) -> SubtitleCue | None:
    if cue.start_us >= end_us or cue.end_us <= start_us:
        return None
    projected_words = [
        projected
        for word in cue.words
        if (projected := _project_word(word, start_us, end_us)) is not None
    ]
    return cue.model_copy(
        update={
            "start_us": max(cue.start_us, start_us) - start_us,
            "end_us": min(cue.end_us, end_us) - start_us,
            "words": projected_words,
        }
    )


def _project_word(word: SubtitleWord, start_us: int, end_us: int) -> SubtitleWord | None:
    if word.start_us >= end_us or word.end_us <= start_us:
        return None
    return word.model_copy(
        update={
            "start_us": max(word.start_us, start_us) - start_us,
            "end_us": min(word.end_us, end_us) - start_us,
        }
    )


def _project_affected(
    item: AffectedRange, start_us: int, end_us: int
) -> AffectedRange | None:
    if item.start_us >= end_us or item.end_us <= start_us:
        return None
    return item.model_copy(
        update={
            "start_us": max(item.start_us, start_us) - start_us,
            "end_us": min(item.end_us, end_us) - start_us,
        }
    )


def _project_dependency(
    item: CacheDependency, start_us: int, end_us: int
) -> CacheDependency | None:
    if item.start_us is None or item.end_us is None:
        return item
    if item.start_us >= end_us or item.end_us <= start_us:
        return None
    return item.model_copy(
        update={
            "start_us": max(item.start_us, start_us) - start_us,
            "end_us": min(item.end_us, end_us) - start_us,
        }
    )
