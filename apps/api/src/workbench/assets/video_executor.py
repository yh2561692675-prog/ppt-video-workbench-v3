from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Protocol

from workbench.assets.derivative_models import DerivativeOperation, DerivativeRequestV1
from workbench.assets.object_store import ContentAddressedObjectStore, StoredObject
from workbench.media.probe import MediaProbeResult, probe_media
from workbench.video.process_runner import (
    CancellableProcessRunner,
    NullProcessControl,
    ProcessControl,
    ProcessResult,
)


class VideoDerivativeError(ValueError):
    pass


class ProcessRunner(Protocol):
    def run(
        self, command: list[str], cwd: Path, control: ProcessControl
    ) -> ProcessResult: ...


class VideoDerivativeExecutor:
    def __init__(
        self,
        object_store: ContentAddressedObjectStore,
        work_root: Path,
        *,
        ffmpeg: str = "ffmpeg",
        process_runner: ProcessRunner | None = None,
        media_probe: Callable[[Path], MediaProbeResult] | None = None,
    ) -> None:
        self.object_store = object_store
        self.work_root = work_root
        self.ffmpeg = ffmpeg
        self.process_runner = process_runner or CancellableProcessRunner()
        self.media_probe = media_probe or probe_media

    def execute(
        self,
        request: DerivativeRequestV1,
        source: Path,
        *,
        control: ProcessControl | None = None,
    ) -> StoredObject:
        if not source.is_file():
            raise VideoDerivativeError("video source does not exist")
        command, suffix = self._command(request, source)
        self.work_root.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(prefix="video-derivative-", dir=self.work_root) as temporary:
            output = Path(temporary) / f"output{suffix}"
            command.append(str(output))
            self.process_runner.run(command, Path(temporary), control or NullProcessControl())
            if not output.is_file() or output.stat().st_size <= 0:
                raise VideoDerivativeError("ffmpeg produced no derivative artifact")
            probe = self.media_probe(output)
            if not any(stream.kind == "video" for stream in probe.streams):
                raise VideoDerivativeError("derivative artifact has no video stream")
            return self.object_store.ingest_file(output, suffix=suffix)

    def _command(self, request: DerivativeRequestV1, source: Path) -> tuple[list[str], str]:
        if request.operation is DerivativeOperation.THUMBNAIL:
            _require_only(request.parameters, {"time_us", "width"})
            time_us = _integer(request.parameters, "time_us", default=0, minimum=0)
            width = _integer(request.parameters, "width", default=640, minimum=1)
            return (
                [
                    self.ffmpeg,
                    "-y",
                    "-loglevel",
                    "error",
                    "-ss",
                    f"{time_us / 1_000_000:.6f}",
                    "-i",
                    str(source),
                    "-frames:v",
                    "1",
                    "-vf",
                    f"scale={width}:-2:flags=lanczos",
                ],
                ".jpg",
            )
        if request.operation not in {
            DerivativeOperation.PROXY,
            DerivativeOperation.TRANSCODE,
        }:
            raise VideoDerivativeError(f"unsupported video operation: {request.operation.value}")
        _require_only(request.parameters, {"width", "crf", "audio_bitrate"})
        width = _integer(request.parameters, "width", default=960, minimum=16)
        crf = _integer(request.parameters, "crf", default=23, minimum=0, maximum=51)
        audio_bitrate = str(request.parameters.get("audio_bitrate", "128k"))
        if not audio_bitrate.endswith("k") or not audio_bitrate[:-1].isdigit():
            raise VideoDerivativeError("audio_bitrate must use integer kbit syntax")
        return (
            [
                self.ffmpeg,
                "-y",
                "-loglevel",
                "error",
                "-i",
                str(source),
                "-map_metadata",
                "0",
                "-vf",
                f"scale='min({width},iw)':-2:flags=lanczos",
                "-c:v",
                "libx264",
                "-crf",
                str(crf),
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-b:a",
                audio_bitrate,
                "-movflags",
                "+faststart",
            ],
            ".mp4",
        )


def _require_only(parameters: dict[str, Any], allowed: set[str]) -> None:
    unknown = sorted(set(parameters) - allowed)
    if unknown:
        raise VideoDerivativeError(f"unsupported video parameters: {', '.join(unknown)}")


def _integer(
    parameters: dict[str, Any],
    key: str,
    *,
    default: int,
    minimum: int,
    maximum: int | None = None,
) -> int:
    try:
        value = int(parameters.get(key, default))
    except (TypeError, ValueError) as error:
        raise VideoDerivativeError(f"video parameter {key} must be an integer") from error
    if value < minimum or (maximum is not None and value > maximum):
        raise VideoDerivativeError(f"video parameter {key} is out of range")
    return value
