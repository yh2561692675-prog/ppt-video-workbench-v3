from __future__ import annotations

import json
import os
import shutil
import subprocess
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, Literal
from uuid import NAMESPACE_URL, UUID, uuid5

from workbench.assets.models import AssetKind, AssetRecord

from .hashing import sha256_file
from .models import MediaProbeMetadata, ResolvedAsset


class AssetResolutionError(ValueError):
    """Raised when an asset record cannot be safely scoped to a project."""


ResolutionMode = Literal["interactive", "authoritative", "final"]
MediaProbe = Callable[[Path], MediaProbeMetadata | Mapping[str, Any]]


class AssetResolver:
    def __init__(
        self,
        project_root: Path,
        records: list[AssetRecord] | None = None,
        *,
        project_id: UUID | None = None,
        media_probe: MediaProbe | None = None,
        ffprobe_executable: str | Path | None = None,
        probe_timeout_s: float = 15.0,
    ) -> None:
        self.project_root = project_root.resolve()
        self.records = records or []
        self.project_id = project_id
        self._media_probe = media_probe or self._probe_with_ffprobe
        self._ffprobe_executable = str(ffprobe_executable) if ffprobe_executable else None
        self._probe_timeout_s = probe_timeout_s
        self.by_ref: dict[str, AssetRecord] = {}
        self.by_id: dict[UUID, AssetRecord] = {}
        for record in self.records:
            if self.project_id is not None and record.project_id != self.project_id:
                raise AssetResolutionError(f"asset {record.asset_id} belongs to another project")
            self.by_id[record.asset_id] = record
            self.by_ref[record.relative_object_path.replace("\\", "/")] = record
            self.by_ref[record.original_name] = record

    def resolve(
        self,
        source_ref: str,
        *,
        asset_id: UUID | None = None,
        kind: str = "unknown",
        resolution_mode: ResolutionMode = "final",
        mode: ResolutionMode | None = None,
    ) -> ResolvedAsset:
        if mode is not None:
            resolution_mode = mode
        lookup_ref = source_ref.replace("\\", "/")
        source_path = self._safe_path(source_ref)
        record = (
            self.by_id.get(asset_id)
            if asset_id is not None
            else self.by_ref.get(lookup_ref) or self.by_ref.get(source_ref)
        )
        if record is None and asset_id is None:
            record = self._record_for_matching_source(source_path, kind)
        if record is None:
            return self._resolve_legacy(source_ref, kind)
        record_path = self._safe_path(record.relative_object_path)
        authoritative_path = source_path if source_path and source_path.is_file() else record_path
        proxy_record = self._select_proxy(record, resolution_mode)
        proxy_path = self._safe_path(proxy_record.relative_object_path) if proxy_record else None
        selected_path = (
            proxy_path if proxy_path is not None and proxy_path.is_file() else authoritative_path
        )
        selected_record = record
        if proxy_record is not None and proxy_path is not None and selected_path == proxy_path:
            selected_record = proxy_record
        observed, probe_status, probe_error = self._probe_asset(record.kind, authoritative_path)
        return ResolvedAsset(
            asset_id=record.asset_id,
            revision=record.revision,
            project_id=record.project_id,
            kind=record.kind.value,
            source_ref=source_ref,
            object_relative_path=record.relative_object_path.replace("\\", "/"),
            proxy_relative_path=self._relative_path(proxy_path),
            resolved_path=self._relative_path(selected_path),
            mime_type=record.mime_type,
            # Keep the catalog hash as the expected value.  Preflight compares
            # it with the file hash and therefore catches replacement after
            # compilation instead of masking it with the observed hash.
            content_hash=selected_record.content_hash,
            exists=bool(selected_path and selected_path.is_file()),
            size_bytes=selected_record.size_bytes,
            duration_us=(
                record.duration_us
                if record.duration_us is not None
                else _field(observed, "duration_us")
            ),
            width=record.width if record.width is not None else _field(observed, "width"),
            height=record.height if record.height is not None else _field(observed, "height"),
            fps_num=record.fps_num if record.fps_num is not None else _field(observed, "fps_num"),
            fps_den=record.fps_den if record.fps_den is not None else _field(observed, "fps_den"),
            media_probe=observed,
            media_probe_status=probe_status,
            media_probe_error=probe_error,
            alpha_mode=record.alpha_mode,
            license_status=record.license.status.value,
            license_expires_at=record.license.expires_at,
            license_snapshot=record.license,
        )

    def _record_for_matching_source(
        self, source_path: Path | None, kind: str
    ) -> AssetRecord | None:
        """Resolve a content-addressed alias only after proving byte identity.

        Import deduplication intentionally stores one record for equal bytes.  A
        project can nevertheless refer to those bytes from several safe paths
        (for example, identical per-page narration WAV files).  Reusing the
        catalog record is safe only when the candidate source still hashes to
        the catalog object and has the requested kind.
        """
        if source_path is None or not source_path.is_file():
            return None
        source_hash = sha256_file(source_path)
        asset_kind = _asset_kind_for_source_kind(kind)
        return next(
            (
                candidate
                for candidate in self.records
                if candidate.kind is asset_kind and candidate.content_hash == source_hash
            ),
            None,
        )

    def _resolve_legacy(self, source_ref: str, kind: str) -> ResolvedAsset:
        path = self._safe_path(source_ref)
        relative = self._relative_path(path)
        exists = bool(path and path.is_file())
        content_hash = sha256_file(path) if exists and path is not None else None
        size_bytes = path.stat().st_size if exists and path is not None else None
        legacy_id = None
        if relative is not None:
            scope = str(self.project_id or self.project_root.name)
            legacy_id = uuid5(NAMESPACE_URL, f"legacy-asset:{scope}:{relative}")
        return ResolvedAsset(
            asset_id=legacy_id,
            revision=1 if legacy_id else None,
            project_id=self.project_id,
            kind=kind,
            source_ref=source_ref,
            object_relative_path=relative,
            resolved_path=relative,
            exists=exists,
            size_bytes=size_bytes,
            content_hash=content_hash,
            legacy_snapshot=relative is not None,
        )

    def _select_proxy(
        self, record: AssetRecord, resolution_mode: ResolutionMode
    ) -> AssetRecord | None:
        if resolution_mode == "final":
            return None
        candidates = [
            candidate
            for candidate in self.records
            if candidate.derived_from == record.asset_id
            and candidate.operation in {"proxy", "transcode"}
            and self._safe_path(candidate.relative_object_path) is not None
        ]
        if not candidates:
            return None
        preferred_tags = (
            {"interactive", "interactive_proxy", "preview", "preview_proxy"}
            if resolution_mode == "interactive"
            else {"authoritative", "authoritative_proxy", "render", "render_proxy"}
        )

        def rank(candidate: AssetRecord) -> tuple[int, int, str]:
            tags = {tag.casefold() for tag in candidate.tags}
            return (
                0 if tags & preferred_tags else 1,
                0 if candidate.operation == "proxy" else 1,
                candidate.relative_object_path.replace("\\", "/"),
            )

        return min(candidates, key=rank)

    def _probe_asset(
        self, kind: AssetKind, path: Path | None
    ) -> tuple[
        MediaProbeMetadata | None,
        Literal["not_requested", "verified", "failed", "unavailable"],
        str | None,
    ]:
        if kind not in {AssetKind.VIDEO, AssetKind.AUDIO} or path is None or not path.is_file():
            return None, "not_requested", None
        try:
            observed = self._media_probe(path)
            return _coerce_probe(observed), "verified", None
        except FileNotFoundError:
            return None, "unavailable", "ffprobe executable is not available"
        except (
            OSError,
            RuntimeError,
            subprocess.SubprocessError,
            TypeError,
            ValueError,
            KeyError,
            AttributeError,
            json.JSONDecodeError,
        ) as exc:
            return None, "failed", _safe_error(exc)

    def _probe_with_ffprobe(self, path: Path) -> MediaProbeMetadata:
        executable = self._ffprobe_executable or _discover_ffprobe()
        if executable is None:
            raise FileNotFoundError("ffprobe")
        result = subprocess.run(
            [executable, "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=self._probe_timeout_s,
            check=False,
        )
        if result.returncode != 0:
            detail = (result.stderr or "ffprobe failed").strip().splitlines()[0]
            raise RuntimeError(detail[:240])
        return _coerce_probe(json.loads(result.stdout))

    def _safe_path(self, relative_path: str) -> Path | None:
        candidate = (self.project_root / relative_path).resolve()
        if candidate != self.project_root and self.project_root not in candidate.parents:
            return None
        return candidate

    def _relative_path(self, path: Path | None) -> str | None:
        if path is None:
            return None
        try:
            return path.relative_to(self.project_root).as_posix()
        except ValueError:
            return None


def _discover_ffprobe() -> str | None:
    configured = os.environ.get("WORKBENCH_FFPROBE")
    if configured:
        return configured
    try:
        from workbench.runtime.layout import RuntimeLayout

        return str(RuntimeLayout.from_environment().require_renderer().ffprobe_executable)
    except Exception:
        return shutil.which("ffprobe")


def _asset_kind_for_source_kind(kind: str) -> AssetKind:
    """Map timeline audio buses to their catalog asset kind."""
    if kind in {"narration", "music", "sfx", "presenter"}:
        return AssetKind.AUDIO
    try:
        return AssetKind(kind)
    except ValueError:
        return AssetKind.DOCUMENT


def _coerce_probe(value: MediaProbeMetadata | Mapping[str, Any]) -> MediaProbeMetadata:
    if isinstance(value, MediaProbeMetadata):
        return value
    if "streams" not in value and any(
        key in value for key in ("width", "height", "duration_us", "fps_num", "fps_den")
    ):
        return MediaProbeMetadata(
            width=_int_or_none(value.get("width")),
            height=_int_or_none(value.get("height")),
            duration_us=_int_or_none(value.get("duration_us")),
            fps_num=_int_or_none(value.get("fps_num")),
            fps_den=_int_or_none(value.get("fps_den")),
        )
    streams = value.get("streams", [])
    if not isinstance(streams, list):
        streams = []
    video = next(
        (
            item
            for item in streams
            if isinstance(item, Mapping) and item.get("codec_type") == "video"
        ),
        {},
    )
    audio = next(
        (
            item
            for item in streams
            if isinstance(item, Mapping) and item.get("codec_type") == "audio"
        ),
        {},
    )
    format_data = value.get("format", {})
    if not isinstance(format_data, Mapping):
        format_data = {}
    stream = video or audio
    duration = format_data.get("duration") or stream.get("duration")
    rate = video.get("avg_frame_rate") or video.get("r_frame_rate")
    return MediaProbeMetadata(
        width=_int_or_none(video.get("width")),
        height=_int_or_none(video.get("height")),
        duration_us=_seconds_to_us(duration),
        fps_num=_rational_part(rate, 0),
        fps_den=_rational_part(rate, 1),
    )


def _field(value: MediaProbeMetadata | None, name: str) -> int | None:
    return getattr(value, name) if value is not None else None


def _int_or_none(value: object) -> int | None:
    if not isinstance(value, (int, float, str)) or isinstance(value, bool):
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number and number > 0 else None


def _seconds_to_us(value: object) -> int | None:
    if not isinstance(value, (int, float, str)) or isinstance(value, bool):
        return None
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        return None
    return round(seconds * 1_000_000) if seconds is not None and seconds >= 0 else None


def _rational_part(value: object, index: int) -> int | None:
    if not isinstance(value, str) or "/" not in value:
        return None
    parts = value.split("/", 1)
    try:
        number = int(parts[index])
    except (IndexError, TypeError, ValueError):
        return None
    return number if number > 0 else None


def _safe_error(exc: Exception) -> str:
    return str(exc).replace("\r", " ").replace("\n", " ")[:240] or exc.__class__.__name__
