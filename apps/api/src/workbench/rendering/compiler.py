from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid5

from workbench.assets.models import AssetRecord
from workbench.cache.contracts import (
    CacheDependency,
    CacheDomain,
    normalize_dependencies,
)
from workbench.continuity.models import AudioCutMode, ContinuityPlan
from workbench.subtitles.workbench_models import SubtitleWorkbenchDocument
from workbench.timeline.production import ClipKind, ProductionTimeline

from .asset_resolver import AssetResolver
from .hashing import sha256_json
from .models import (
    AffectedRange,
    AudioMixClip,
    AudioMixPlan,
    GraphCanvas,
    RenderGraphV2,
    RenderNodeV2,
    ResolvedAsset,
    SubtitleCue,
    SubtitleRenderPlan,
    SubtitleWord,
    TransitionEdge,
)
from .timebase import us_range_to_frames

COMPILER_VERSION = "rendergraph-v2-0.2"


class RenderGraphCompiler:
    """Compile all editable sources into one deterministic execution graph."""

    def compile(
        self,
        timeline: ProductionTimeline,
        *,
        continuity: ContinuityPlan | None = None,
        subtitles: SubtitleWorkbenchDocument | None = None,
        assets: list[AssetRecord] | None = None,
        project_root: Any | None = None,
        source_revisions: dict[str, str] | None = None,
    ) -> RenderGraphV2:
        timeline = ProductionTimeline.model_validate(timeline.model_dump(mode="python"))
        # A caller that has not supplied an asset catalog is compiling a
        # metadata-only graph (for example an offline migration fixture).  Do
        # not manufacture missing ResolvedAsset records in that mode; strict
        # asset checks apply once an authoritative catalog is supplied.
        resolver = (
            AssetResolver(project_root, assets, project_id=timeline.project_id)
            if project_root is not None and assets is not None
            else None
        )
        namespace = timeline.project_id
        nodes: list[RenderNodeV2] = []
        node_by_clip: dict[UUID, RenderNodeV2] = {}
        resolved_assets = {}
        for track in sorted(timeline.tracks, key=lambda item: item.order):
            previous: UUID | None = None
            for clip in sorted(track.clips, key=lambda item: (item.start_us, str(item.id))):
                node_id = uuid5(namespace, f"render-graph-v2:{timeline.revision}:{clip.id}")
                payload = dict(clip.payload)
                asset = (
                    resolver.resolve(clip.source_ref, kind=clip.kind.value)
                    if resolver is not None
                    else None
                )
                if asset is not None:
                    resolved_assets[asset.source_ref] = asset
                node = RenderNodeV2(
                    id=node_id,
                    clip_id=clip.id,
                    track_id=track.id,
                    kind=clip.kind.value,
                    start_us=clip.start_us,
                    end_us=clip.end_us,
                    start_frame=us_range_to_frames(clip.start_us, clip.end_us, timeline.fps).start,
                    end_frame_exclusive=us_range_to_frames(
                        clip.start_us, clip.end_us, timeline.fps
                    ).end,
                    track_order=track.order,
                    source_in_us=clip.source_in_us,
                    source_ref=clip.source_ref,
                    asset_id=asset.asset_id if asset else None,
                    asset_revision=asset.revision if asset else None,
                    z_index=_as_int(payload.get("z_index"), track.order),
                    blend_mode=str(payload.get("blend_mode", "normal")),
                    opacity=_as_float(payload.get("opacity"), 1.0),
                    payload=payload,
                    depends_on=[previous] if previous else [],
                    cache_key=sha256_json(
                        {
                            "clip": clip.model_dump(mode="json"),
                            "timeline_hash": timeline.content_hash,
                            "compiler_version": COMPILER_VERSION,
                        }
                    ),
                )
                nodes.append(node)
                node_by_clip[clip.id] = node
                previous = node_id

        transitions = self._compile_transitions(continuity, node_by_clip, nodes)
        self._compile_overlays(
            continuity, namespace, timeline, nodes, node_by_clip, resolved_assets, resolver
        )
        audio = self._compile_audio(timeline, nodes, transitions)
        subtitle_plan = self._compile_subtitles(subtitles)
        ranges = self._affected_ranges(transitions, subtitle_plan, nodes)
        dependencies = self._cache_dependencies(
            nodes, transitions, subtitle_plan, resolved_assets, timeline
        )
        graph = RenderGraphV2(
            graph_id=uuid5(namespace, f"render-graph-v2:{timeline.revision}"),
            project_id=timeline.project_id,
            timeline_revision=timeline.revision,
            timeline_hash=timeline.content_hash or sha256_json(timeline.model_dump(mode="json")),
            compiler_version=COMPILER_VERSION,
            duration_us=timeline.duration_us,
            canvas=GraphCanvas(
                width=timeline.width,
                height=timeline.height,
                fps=timeline.fps,
                fps_num=timeline.fps,
                fps_den=1,
                duration_us=timeline.duration_us,
                aspect_ratio=f"{timeline.width}:{timeline.height}",
            ),
            nodes=nodes,
            transitions=transitions,
            assets=list(resolved_assets.values()),
            audio=audio,
            subtitles=subtitle_plan,
            source_revisions={
                "timeline": timeline.content_hash or sha256_json(timeline.model_dump(mode="json")),
                **(source_revisions or {}),
            },
            cache_dependencies=list(dependencies),
            affected_ranges=ranges,
            graph_hash="0" * 64,
            created_at=datetime.now(UTC),
        )
        payload = graph.model_dump(mode="json", exclude={"graph_hash", "created_at"})
        return graph.model_copy(update={"graph_hash": sha256_json(payload)})

    def _compile_transitions(
        self,
        continuity: ContinuityPlan | None,
        node_by_clip: dict[UUID, RenderNodeV2],
        nodes: list[RenderNodeV2],
    ) -> list[TransitionEdge]:
        if continuity is None:
            return []
        by_page = {
            node.payload.get("page_id"): node
            for node in nodes
            if node.kind in {ClipKind.SLIDE.value, ClipKind.PRESENTER.value}
            and node.payload.get("page_id")
        }
        edges: list[TransitionEdge] = []
        for spec in continuity.transitions:
            if not spec.enabled:
                continue
            source = by_page.get(str(spec.from_page_id))
            target = by_page.get(str(spec.to_page_id))
            if source is None or target is None:
                raise ValueError("transition references a page that is missing from the timeline")
            duration_us = spec.duration_ms * 1_000
            start_us = max(source.start_us, target.start_us - duration_us)
            edge = TransitionEdge(
                id=spec.id,
                from_node_id=source.id,
                to_node_id=target.id,
                kind=spec.kind.value,
                start_us=start_us,
                end_us=start_us + duration_us,
                easing=spec.easing,
                audio_mode=spec.audio_mode.value,
                audio_offset_us=spec.audio_offset_ms * 1_000,
                chapter_boundary=spec.chapter_boundary,
                parameters=spec.parameters,
            )
            edges.append(edge)
        return edges

    def _compile_overlays(
        self,
        continuity: ContinuityPlan | None,
        namespace: UUID,
        timeline: ProductionTimeline,
        nodes: list[RenderNodeV2],
        node_by_clip: dict[UUID, RenderNodeV2],
        resolved_assets: dict[str, Any],
        resolver: AssetResolver | None,
    ) -> None:
        if continuity is None:
            return
        for overlay in continuity.overlays:
            source = (
                resolver.resolve(
                    overlay.source_ref, asset_id=overlay.license_asset_id, kind=overlay.kind
                )
                if resolver is not None
                else None
            )
            if source is not None:
                resolved_assets[source.source_ref] = source
            node = RenderNodeV2(
                id=uuid5(namespace, f"render-graph-v2:overlay:{overlay.id}"),
                kind="overlay",
                start_us=overlay.start_ms * 1_000,
                end_us=(overlay.start_ms + overlay.duration_ms) * 1_000,
                source_ref=overlay.source_ref,
                asset_id=source.asset_id if source else None,
                asset_revision=source.revision if source else None,
                z_index=overlay.z_index,
                opacity=overlay.opacity,
                payload=overlay.model_dump(mode="json"),
            )
            nodes.append(node)

    def _compile_audio(
        self,
        timeline: ProductionTimeline,
        nodes: list[RenderNodeV2],
        transitions: list[TransitionEdge],
    ) -> AudioMixPlan:
        clips: list[AudioMixClip] = []
        for node in nodes:
            if node.kind not in {
                ClipKind.NARRATION.value,
                ClipKind.PRESENTER.value,
                ClipKind.MUSIC.value,
                ClipKind.SFX.value,
            }:
                continue
            bus = "presenter" if node.kind == ClipKind.PRESENTER.value else node.kind
            if bus not in {"narration", "presenter", "music", "sfx"}:
                bus = "narration"
            clips.append(
                AudioMixClip(
                    id=node.id,
                    kind=node.kind,
                    source_ref=node.source_ref,
                    asset_id=node.asset_id,
                    asset_revision=node.asset_revision,
                    timeline_start_us=node.start_us,
                    timeline_end_us=min(node.end_us, timeline.duration_us),
                    source_in_us=node.source_in_us,
                    source_duration_us=(
                        int(node.payload["source_duration_us"])
                        if node.payload.get("source_duration_us") is not None
                        else None
                    ),
                    bus=bus,  # type: ignore[arg-type]
                    gain_db=float(node.payload.get("gain_db", 0)),
                    fade_in_us=int(node.payload.get("fade_in_us", 0)),
                    fade_out_us=int(node.payload.get("fade_out_us", 0)),
                )
            )
        by_node = {clip.id: clip for clip in clips}
        for edge in transitions:
            if edge.audio_mode == AudioCutMode.J_CUT.value:
                target = by_node.get(edge.to_node_id)
                if target:
                    target.timeline_start_us = max(
                        0, target.timeline_start_us - abs(edge.audio_offset_us)
                    )
            elif edge.audio_mode == AudioCutMode.L_CUT.value:
                previous = by_node.get(edge.from_node_id)
                if previous:
                    previous.timeline_end_us = min(
                        timeline.duration_us,
                        previous.timeline_end_us + abs(edge.audio_offset_us),
                    )
        return AudioMixPlan(clips=clips)

    def _compile_subtitles(self, document: SubtitleWorkbenchDocument | None) -> SubtitleRenderPlan:
        if document is None:
            return SubtitleRenderPlan()
        cues: list[SubtitleCue] = []
        languages: list[str] = []
        for track in document.tracks:
            languages.append(track.language)
            for cue in track.cues:
                cues.append(
                    SubtitleCue(
                        id=cue.id,
                        language=track.language,
                        label=track.label,
                        start_us=cue.start_ms * 1_000,
                        end_us=cue.end_ms * 1_000,
                        text=cue.text,
                        translation=cue.translation,
                        words=[
                            SubtitleWord(
                                text=word.text,
                                start_us=word.start_ms * 1_000,
                                end_us=word.end_ms * 1_000,
                            )
                            for word in cue.words
                        ],
                        line_breaks=cue.line_breaks,
                        style=(cue.style_override or document.default_style).model_dump(
                            mode="json"
                        ),
                    )
                )
        modes = {
            "soft": "soft",
            "burn_in": "burn_in",
            "both": "both",
            "none": "none",
        }
        mode = modes.get(document.render_mode.value, "soft")
        return SubtitleRenderPlan(
            render_mode=mode,  # type: ignore[arg-type]
            cues=cues,
            languages=languages,
            default_style=document.default_style.model_dump(mode="json"),
            document_revision=document.revision,
            document_hash=document.content_hash
            or sha256_json(document.model_dump(mode="json", exclude={"content_hash"})),
            tracks=[
                {
                    "id": str(track.id),
                    "language": track.language,
                    "label": track.label,
                    "primary": track.primary,
                    "visible": track.visible,
                }
                for track in document.tracks
            ],
        )

    def _affected_ranges(
        self,
        transitions: list[TransitionEdge],
        subtitles: SubtitleRenderPlan,
        nodes: list[RenderNodeV2],
    ) -> list[AffectedRange]:
        ranges: list[AffectedRange] = []
        for edge in transitions:
            if edge.end_us > edge.start_us:
                ranges.append(
                    AffectedRange(
                        start_us=edge.start_us,
                        end_us=edge.end_us,
                        reasons=[f"transition:{edge.kind}", f"audio:{edge.audio_mode}"],
                    )
                )
        for cue in subtitles.cues:
            ranges.append(
                AffectedRange(
                    start_us=cue.start_us,
                    end_us=cue.end_us,
                    reasons=[f"subtitle:{subtitles.render_mode}"],
                )
            )
        for node in nodes:
            if node.kind == ClipKind.OVERLAY.value:
                ranges.append(
                    AffectedRange(
                        start_us=node.start_us,
                        end_us=node.end_us,
                        reasons=["overlay"],
                    )
                )
        return _merge_affected_ranges(ranges)

    def _cache_dependencies(
        self,
        nodes: list[RenderNodeV2],
        transitions: list[TransitionEdge],
        subtitles: SubtitleRenderPlan,
        resolved_assets: Mapping[str, ResolvedAsset],
        timeline: ProductionTimeline,
    ) -> tuple[CacheDependency, ...]:
        dependencies: list[CacheDependency] = []
        for node in nodes:
            if node.kind in {ClipKind.NARRATION.value, ClipKind.MUSIC.value, ClipKind.SFX.value}:
                domain = CacheDomain.AUDIO
            elif node.kind == ClipKind.OVERLAY.value:
                domain = CacheDomain.OVERLAY
            else:
                domain = CacheDomain.VIDEO_ONLY
            asset = resolved_assets.get(node.source_ref)
            asset_hash = getattr(asset, "content_hash", None)
            upstream_hash = asset_hash if isinstance(asset_hash, str) else node.cache_key
            if upstream_hash is None:
                upstream_hash = sha256_json({"source_ref": node.source_ref})
            dependencies.append(
                CacheDependency(
                    domain=domain,
                    node_key=f"{domain.value}:{node.id}",
                    upstream_kind="asset_revision" if node.asset_id else "source_revision",
                    upstream_key=str(node.asset_id or node.source_ref),
                    upstream_hash=upstream_hash,
                    start_us=node.start_us,
                    end_us=node.end_us,
                )
            )
        for edge in transitions:
            range_start = edge.start_us if edge.end_us > edge.start_us else None
            range_end = edge.end_us if edge.end_us > edge.start_us else None
            edge_hash = sha256_json(edge.model_dump(mode="json"))
            dependencies.append(
                CacheDependency(
                    domain=CacheDomain.TRANSITION,
                    node_key=f"transition:{edge.id}",
                    upstream_kind="continuity_revision",
                    upstream_key=str(edge.id),
                    upstream_hash=edge_hash,
                    start_us=range_start,
                    end_us=range_end,
                )
            )
            if edge.audio_mode != "cut":
                dependencies.append(
                    CacheDependency(
                        domain=CacheDomain.AUDIO,
                        node_key=f"audio-transition:{edge.id}",
                        upstream_kind="continuity_revision",
                        upstream_key=str(edge.id),
                        upstream_hash=edge_hash,
                        start_us=range_start,
                        end_us=range_end,
                    )
                )
        subtitle_domains: tuple[CacheDomain, ...] = {
            "soft": (CacheDomain.SUBTITLE_SOFT,),
            "burn_in": (CacheDomain.SUBTITLE_BURN_IN,),
            "both": (CacheDomain.SUBTITLE_SOFT, CacheDomain.SUBTITLE_BURN_IN),
            "none": (),
        }[subtitles.render_mode]
        for cue in subtitles.cues:
            for domain in subtitle_domains:
                dependencies.append(
                    CacheDependency(
                        domain=domain,
                        node_key=f"{domain.value}:{cue.id}",
                        upstream_kind="subtitle_revision",
                        upstream_key=str(cue.id),
                        upstream_hash=subtitles.document_hash,
                        start_us=cue.start_us,
                        end_us=cue.end_us,
                    )
                )
        dependencies.extend(
            [
                CacheDependency(
                    domain=CacheDomain.LAYOUT,
                    node_key="layout:canvas",
                    upstream_kind="timeline_revision",
                    upstream_key=str(timeline.project_id),
                    upstream_hash=sha256_json(
                        {
                            "width": timeline.width,
                            "height": timeline.height,
                            "fps": timeline.fps,
                        }
                    ),
                    start_us=0,
                    end_us=timeline.duration_us,
                ),
                CacheDependency(
                    domain=CacheDomain.FINAL,
                    node_key="compiler:rendergraph-v2",
                    upstream_kind="compiler",
                    upstream_key=COMPILER_VERSION,
                    upstream_hash=sha256_json({"compiler_version": COMPILER_VERSION}),
                ),
            ]
        )
        return normalize_dependencies(dependencies)


def _merge_affected_ranges(ranges: list[AffectedRange]) -> list[AffectedRange]:
    merged: list[AffectedRange] = []
    for item in sorted(ranges, key=lambda value: (value.start_us, value.end_us)):
        if not merged or item.start_us > merged[-1].end_us:
            merged.append(item.model_copy(update={"reasons": sorted(set(item.reasons))}))
            continue
        previous = merged[-1]
        merged[-1] = AffectedRange(
            start_us=previous.start_us,
            end_us=max(previous.end_us, item.end_us),
            reasons=sorted(set(previous.reasons + item.reasons)),
        )
    return merged


def _as_int(value: object, default: int) -> int:
    return int(value) if isinstance(value, (str, int, float)) else default


def _as_float(value: object, default: float) -> float:
    return float(value) if isinstance(value, (str, int, float)) else default
