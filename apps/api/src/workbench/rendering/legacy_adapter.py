from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Literal, cast
from uuid import UUID, uuid5

from pydantic import BaseModel, ConfigDict, Field

from workbench.timeline.production import (
    ClipKind,
    ProductionTimeline,
    TimelineClip,
    TimelineTrack,
    with_content_hash,
)

from .asset_resolver import AssetResolver
from .hashing import sha256_file, sha256_json
from .models import ResolvedAsset, SubtitleCue, SubtitleRenderPlan


class LegacyFallbackForbidden(RuntimeError):
    pass


class LegacyAdapterIssue(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    code: str = Field(min_length=1, max_length=80)
    severity: Literal["warning", "confirmation", "blocking"]
    message: str = Field(min_length=1, max_length=500)
    source_ref: str | None = Field(default=None, max_length=500)


class LegacyProjectView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    project_id: UUID
    timeline: ProductionTimeline
    assets: tuple[ResolvedAsset, ...]
    subtitles: SubtitleRenderPlan
    issues: tuple[LegacyAdapterIssue, ...]
    source_hashes: dict[str, str]
    manifest_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    v1_export_allowed: bool = True


class LegacyProjectAdapter:
    """Build a deterministic read-only compatibility view of a V1 project."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root.resolve()

    def open(
        self,
        payload: Mapping[str, Any],
        *,
        renderer_generation: Literal["v1", "v2"] = "v1",
    ) -> LegacyProjectView:
        if renderer_generation == "v2":
            raise LegacyFallbackForbidden(
                "V2-exclusive project cannot silently fall back to the legacy adapter"
            )
        project_id = UUID(str(payload["id"]))
        manifest_hash = sha256_json(dict(payload))
        pages = payload.get("pages")
        if not isinstance(pages, list) or not pages:
            raise ValueError("legacy project has no pages")
        issues: list[LegacyAdapterIssue] = []
        slide_track_id = uuid5(project_id, "legacy-track:slides")
        audio_track_id = uuid5(project_id, "legacy-track:narration")
        slides: list[TimelineClip] = []
        audio: list[TimelineClip] = []
        source_refs: list[tuple[str, str]] = []
        cursor_us = 0
        seen_orders: set[int] = set()
        page_windows: list[tuple[UUID, int, int]] = []
        for index, raw_page in enumerate(pages, start=1):
            page = _mapping(raw_page)
            legacy_order = _positive_int(page.get("order"), index)
            if legacy_order in seen_orders:
                issues.append(
                    LegacyAdapterIssue(
                        code="legacy_duplicate_page_order",
                        severity="confirmation",
                        message=f"duplicate legacy page order {legacy_order} was normalized",
                    )
                )
            seen_orders.add(legacy_order)
            page_id = uuid5(project_id, f"legacy-page:{index}")
            timeline = _mapping(page.get("timeline"))
            audio_data = _mapping(page.get("audio"))
            start_ms = max(
                cursor_us // 1_000,
                _nonnegative_int(timeline.get("start_ms"), cursor_us // 1_000),
            )
            default_duration_ms = _positive_int(audio_data.get("duration_ms"), 3_000)
            end_ms = _positive_int(timeline.get("end_ms"), start_ms + default_duration_ms)
            if end_ms <= start_ms:
                end_ms = start_ms + default_duration_ms
                issues.append(
                    LegacyAdapterIssue(
                        code="legacy_timeline_repaired",
                        severity="warning",
                        message=f"page {index} had an invalid timeline range",
                    )
                )
            start_us = start_ms * 1_000
            end_us = end_ms * 1_000
            cursor_us = end_us
            page_windows.append((page_id, start_us, end_us))
            image_ref = _source_ref(page.get("preview_path") or page.get("image_path"))
            if image_ref is None:
                image_ref = f"legacy-missing/page-{index:04d}.png"
                issues.append(
                    LegacyAdapterIssue(
                        code="legacy_page_media_missing",
                        severity="blocking",
                        message=f"page {index} has no image source",
                        source_ref=image_ref,
                    )
                )
            elif _is_absolute_windows(image_ref):
                issues.append(
                    LegacyAdapterIssue(
                        code="legacy_absolute_path_outside_project",
                        severity="blocking",
                        message=f"page {index} uses an external absolute path",
                        source_ref=image_ref,
                    )
                )
            slides.append(
                TimelineClip(
                    id=uuid5(project_id, f"legacy-clip:slide:{index}"),
                    track_id=slide_track_id,
                    kind=ClipKind.SLIDE,
                    start_us=start_us,
                    duration_us=end_us - start_us,
                    source_ref=image_ref,
                    payload={
                        "page_id": str(page_id),
                        "legacy_order": legacy_order,
                        "normalized_order": index,
                        "title": str(page.get("title") or ""),
                    },
                    locked=True,
                )
            )
            source_refs.append((image_ref, ClipKind.SLIDE.value))
            audio_ref = _source_ref(audio_data.get("relative_path"))
            if audio_ref is not None:
                audio.append(
                    TimelineClip(
                        id=uuid5(project_id, f"legacy-clip:audio:{index}"),
                        track_id=audio_track_id,
                        kind=ClipKind.NARRATION,
                        start_us=start_us,
                        duration_us=end_us - start_us,
                        source_ref=audio_ref,
                        payload={"page_id": str(page_id), "normalized_order": index},
                        locked=True,
                    )
                )
                source_refs.append((audio_ref, ClipKind.NARRATION.value))
            else:
                issues.append(
                    LegacyAdapterIssue(
                        code="legacy_page_audio_missing",
                        severity="warning",
                        message=f"page {index} has no narration audio",
                    )
                )
        tracks = [
            TimelineTrack(
                id=slide_track_id,
                kind=ClipKind.SLIDE,
                name="Legacy slides",
                order=0,
                locked=True,
                clips=slides,
            ),
            TimelineTrack(
                id=audio_track_id,
                kind=ClipKind.NARRATION,
                name="Legacy narration",
                order=1,
                locked=True,
                clips=audio,
            ),
        ]
        timeline_view = with_content_hash(
            ProductionTimeline(
                project_id=project_id,
                revision=1,
                fps=_positive_int(payload.get("fps"), 30),
                width=_positive_int(payload.get("width"), 1920),
                height=_positive_int(payload.get("height"), 1080),
                duration_us=cursor_us,
                tracks=tracks,
                input_fingerprint=manifest_hash,
            )
        )
        resolver = AssetResolver(self.project_root, project_id=project_id)
        assets_by_ref: dict[str, ResolvedAsset] = {}
        source_hashes: dict[str, str] = {}
        for source_ref, kind in source_refs:
            if source_ref not in assets_by_ref:
                asset = resolver.resolve(source_ref, kind=kind)
                assets_by_ref[source_ref] = asset
                if asset.exists and asset.content_hash is not None:
                    source_hashes[source_ref] = asset.content_hash
                elif not _is_absolute_windows(source_ref):
                    issues.append(
                        LegacyAdapterIssue(
                            code="legacy_asset_missing",
                            severity="blocking",
                            message="legacy asset is missing",
                            source_ref=source_ref,
                        )
                    )
        subtitles = _subtitle_plan(payload, project_id, page_windows)
        for relative in _protected_legacy_paths(payload):
            path = _contained_path(self.project_root, relative)
            if path is not None and path.is_file():
                source_hashes.setdefault(relative, sha256_file(path))
        return LegacyProjectView(
            project_id=project_id,
            timeline=timeline_view,
            assets=tuple(assets_by_ref.values()),
            subtitles=subtitles,
            issues=tuple(issues),
            source_hashes=dict(sorted(source_hashes.items())),
            manifest_hash=manifest_hash,
        )

    def open_manifest(
        self,
        manifest_path: Path,
        *,
        renderer_generation: Literal["v1", "v2"] = "v1",
    ) -> LegacyProjectView:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("legacy manifest must be an object")
        return self.open(payload, renderer_generation=renderer_generation)


def _subtitle_plan(
    payload: Mapping[str, Any],
    project_id: UUID,
    page_windows: list[tuple[UUID, int, int]],
) -> SubtitleRenderPlan:
    raw_cues = payload.get("subtitle_cues")
    cues: list[SubtitleCue] = []
    if isinstance(raw_cues, list):
        for index, raw in enumerate(raw_cues):
            if not isinstance(raw, Mapping):
                continue
            start_us = _nonnegative_int(raw.get("start_ms"), 0) * 1_000
            end_us = _positive_int(raw.get("end_ms"), start_us // 1_000 + 1) * 1_000
            text = str(raw.get("text") or "").strip()
            if not text or end_us <= start_us:
                continue
            cues.append(
                SubtitleCue(
                    id=uuid5(project_id, f"legacy-subtitle:{index}:{start_us}:{end_us}"),
                    language=str(raw.get("language") or "zh-CN"),
                    label=str(raw.get("language") or "zh-CN"),
                    start_us=start_us,
                    end_us=end_us,
                    text=text,
                    style={"legacy": True},
                )
            )
    document_hash = sha256_json([cue.model_dump(mode="json") for cue in cues])
    return SubtitleRenderPlan(
        render_mode="soft",
        cues=cues,
        languages=sorted({cue.language for cue in cues}),
        document_revision=1,
        document_hash=document_hash,
        tracks=[{"legacy": True, "page_count": len(page_windows)}],
    )


def _protected_legacy_paths(payload: Mapping[str, Any]) -> list[str]:
    paths: list[str] = []
    subtitle = payload.get("subtitle_artifact")
    export = payload.get("video_export")
    if isinstance(subtitle, Mapping) and isinstance(subtitle.get("srt_relative_path"), str):
        paths.append(str(subtitle["srt_relative_path"]))
    if isinstance(export, Mapping) and isinstance(export.get("mp4_relative_path"), str):
        paths.append(str(export["mp4_relative_path"]))
    return paths


def _contained_path(root: Path, source_ref: str) -> Path | None:
    if _is_absolute_windows(source_ref):
        return None
    relative = PurePosixPath(source_ref.replace("\\", "/"))
    if relative.is_absolute() or ".." in relative.parts:
        return None
    candidate = root.joinpath(*relative.parts).resolve(strict=False)
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    return candidate


def _is_absolute_windows(value: str) -> bool:
    return PureWindowsPath(value).is_absolute()


def _source_ref(value: object) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def _mapping(value: object) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    return cast(Mapping[str, Any], value)


def _positive_int(value: object, default: int) -> int:
    if not isinstance(value, (str, int, float)):
        return default
    try:
        result = int(value)
    except (TypeError, ValueError):
        return default
    return result if result > 0 else default


def _nonnegative_int(value: object, default: int) -> int:
    if not isinstance(value, (str, int, float)):
        return default
    try:
        result = int(value)
    except (TypeError, ValueError):
        return default
    return result if result >= 0 else default
