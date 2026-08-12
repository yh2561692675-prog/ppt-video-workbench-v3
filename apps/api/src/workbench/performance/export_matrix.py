"""Real-media DP44 output-profile acceptance for the V1 delivery path.

Each matrix entry goes through the product ``VideoExportService`` rather than
only constructing an export plan.  The fixture deliberately has one page so
it proves the output profile without duplicating the S50 scale acceptance.
"""

from __future__ import annotations

import hashlib
import json
import time
import wave
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from PIL import Image

from workbench.audio.models import Transcript, TranscriptWord
from workbench.domain.confirmation import Confirmation
from workbench.domain.enums import NodeStatus
from workbench.domain.extraction import PageExtraction
from workbench.domain.models import AudioRecord, NarrationRecord, PageRecord
from workbench.main import create_app
from workbench.video.models import ProjectVideoProps
from workbench.video.package_service import VideoExportResult, validate_media_probe

from .s50_acceptance import FfmpegPageRenderer, sha256_file

_SCHEMA_VERSION = "1.0"
_PAGE_DURATION_MS = 1_000
_PROJECT_NAME = "m"


@dataclass(frozen=True, slots=True)
class OutputProfileCase:
    id: str
    width: int
    height: int
    fps: int
    purpose: str


# The five cases cover every V1 delivery dimension required by DP44 while
# keeping the actual matrix compact enough for routine Windows acceptance.
EXECUTABLE_OUTPUT_MATRIX: tuple[OutputProfileCase, ...] = (
    OutputProfileCase("landscape-720p-24", 1280, 720, 24, "16:9 720p"),
    OutputProfileCase("landscape-720p-25", 1280, 720, 25, "16:9 720p"),
    OutputProfileCase("landscape-1080p-30", 1920, 1080, 30, "16:9 1080p"),
    OutputProfileCase("portrait-1080p-60", 1080, 1920, 60, "9:16 1080p"),
    OutputProfileCase("square-1080p-30", 1080, 1080, 30, "1:1 1080p"),
)


@dataclass(frozen=True, slots=True)
class MatrixFixture:
    project_id: UUID
    project_root: Path
    source_manifest_sha256: str


@dataclass(frozen=True, slots=True)
class MatrixCaseResult:
    profile: OutputProfileCase
    result: VideoExportResult
    media_probe: dict[str, object]
    elapsed_ms: int
    final_sha256: str
    package_config_sha256: str
    subtitle_present: bool


def execute_output_matrix(
    run_root: Path,
    *,
    ffmpeg: str,
    ffprobe: str,
) -> tuple[MatrixFixture, tuple[MatrixCaseResult, ...]]:
    """Run the executable 720p/1080p output matrix in a new owned workspace."""

    run_root = run_root.resolve()
    if run_root.exists():
        raise FileExistsError(f"output matrix run root already exists: {run_root}")
    run_root.mkdir(parents=True)
    workspace = run_root / "workspace"
    workspace.mkdir()
    app = create_app(workspace, video_renderer=FfmpegPageRenderer(ffmpeg))
    exporter = app.state.video_export_service
    exporter.ffmpeg = ffmpeg
    exporter.ffprobe = ffprobe
    fixture = _create_fixture(app.state.project_service)
    exporter.preview.subtitles.build(fixture.project_id)
    preflight = exporter.preview.preflight(fixture.project_id)
    if not preflight.allowed or preflight.props is None:
        raise RuntimeError("DP44 fixture preflight was blocked")

    results: list[MatrixCaseResult] = []
    for profile in EXECUTABLE_OUTPUT_MATRIX:
        props = _profile_props(preflight.props, profile)
        started = time.perf_counter()
        result = exporter.export(fixture.project_id, props_override=props)
        elapsed_ms = round((time.perf_counter() - started) * 1_000)
        final_path = fixture.project_root / result.mp4_relative_path
        package_root = fixture.project_root / result.package_relative_path
        package_config = package_root / "render.config.json"
        subtitle = package_root / "字幕.srt"
        probe = exporter._probe(final_path)
        validate_media_probe(
            probe,
            expected_duration_ms=_PAGE_DURATION_MS,
            tolerance_ms=150,
            expected_width=profile.width,
            expected_height=profile.height,
            expected_fps=profile.fps,
        )
        if not package_config.is_file() or not subtitle.is_file():
            raise RuntimeError(
                "DP44 package is missing its frozen render config or subtitle artifact"
            )
        config = json.loads(package_config.read_text(encoding="utf-8"))
        if config != {"width": profile.width, "height": profile.height, "fps": profile.fps}:
            raise RuntimeError(
                "DP44 package render config does not match the executed output profile"
            )
        results.append(
            MatrixCaseResult(
                profile=profile,
                result=result,
                media_probe=probe,
                elapsed_ms=elapsed_ms,
                final_sha256=sha256_file(final_path),
                package_config_sha256=sha256_file(package_config),
                subtitle_present=subtitle.is_file() and subtitle.stat().st_size > 0,
            )
        )
    return fixture, tuple(results)


def run_output_matrix_acceptance(
    *,
    repo_root: Path,
    candidate: dict[str, object],
    candidate_manifest_path: Path,
    output_root: Path,
    ffmpeg: str,
    ffprobe: str,
) -> Path:
    """Write immutable candidate-bound DP44 evidence below ignored test-results."""

    repo_root = repo_root.resolve()
    output_root = output_root.resolve()
    allowed = (repo_root / "test-results").resolve()
    try:
        output_root.relative_to(allowed)
    except ValueError as error:
        raise ValueError("output_root must remain inside repository test-results") from error
    candidate_id, source_commit = _candidate_identity(candidate)
    run_id = f"matrix-{time.strftime('%Y%m%dT%H%M%SZ')}-{uuid4().hex[:8]}"
    run_root = output_root / candidate_id / run_id
    fixture, cases = execute_output_matrix(run_root, ffmpeg=ffmpeg, ffprobe=ffprobe)
    evidence_path = run_root / "output-matrix-acceptance-v1.json"
    payload = {
        "schema_version": _SCHEMA_VERSION,
        "status": "passed",
        "run_id": run_id,
        "candidate": {
            "candidate_id": candidate_id,
            "source_commit": source_commit,
            "manifest_sha256": sha256_file(candidate_manifest_path),
        },
        "fixture": {
            "id": "DP44-one-page-synthetic-v1",
            "duration_ms": _PAGE_DURATION_MS,
            "source_manifest_sha256": fixture.source_manifest_sha256,
            "content_policy": "generated image plus generated WAV only",
        },
        "executed": [_case_payload(case) for case in cases],
        "admission": {
            "four_k": "not executed; requires feature flag plus launcher-confirmed hardware",
            "gif": "not executed; explicitly blocked before V1 video queueing",
        },
        "scope": {
            "executed": "V1 page render, FFmpeg mux, final media probe, package config and SRT",
            "separate_rendergraph_contract": [
                "soft subtitles",
                "burn-in subtitles",
                "overlay",
                "transition",
                "audio mix",
            ],
        },
    }
    _write_new_json(evidence_path, payload)
    return evidence_path


def _profile_props(props: ProjectVideoProps, profile: OutputProfileCase) -> ProjectVideoProps:
    return props.model_copy(
        update={"width": profile.width, "height": profile.height, "fps": profile.fps}
    )


def _create_fixture(projects: Any) -> MatrixFixture:
    project = projects.create(_PROJECT_NAME)
    root = (projects.workspace_root / project.project_dir).resolve()
    page_id = uuid4()
    revision_id = uuid4()
    image = root / "02_pages" / "page-0001.png"
    audio = root / "05_audio" / "page-0001.wav"
    image.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (640, 360), (41, 97, 173)).save(image, format="PNG")
    _write_wav(audio, _PAGE_DURATION_MS)
    audio_relative = audio.relative_to(root).as_posix()
    page = PageRecord(
        id=page_id,
        order=1,
        title="DP44 synthetic page",
        narration=NarrationRecord(
            id=uuid4(),
            revision_id=revision_id,
            confirmed_revision_id=revision_id,
            text="Synthetic DP44 output profile fixture.",
            status=NodeStatus.COMPLETED,
            author="performance-fixture",
        ),
        audio=AudioRecord(
            id=uuid4(),
            status=NodeStatus.COMPLETED,
            source="heygen",
            relative_path=audio_relative,
            duration_ms=_PAGE_DURATION_MS,
            cache_key=sha256_file(audio),
            narration_revision_id=revision_id,
            voice_id="synthetic-local-fixture",
        ),
    )
    projects.save(
        project.model_copy(
            update={
                "pages": [page],
                "page_extractions": [
                    PageExtraction(
                        id=uuid4(),
                        order=1,
                        title="DP44 synthetic page",
                        preview_path=image,
                        extraction_method="image",
                        source_ref="DP44-one-page-synthetic-v1",
                    )
                ],
                "narration_confirmations": [
                    Confirmation(
                        id=uuid4(),
                        page_id=page_id,
                        revision_id=revision_id,
                        actor="performance-fixture",
                        confirmed_at=datetime.now(UTC),
                    )
                ],
                "transcript": Transcript(
                    words=[
                        TranscriptWord(
                            text="DP44 synthetic",
                            start_ms=50,
                            end_ms=950,
                            confidence=1.0,
                        )
                    ],
                    detected_language="en",
                    model="synthetic-dp44-fixture",
                    device="cpu",
                    created_at=datetime.now(UTC),
                ),
            }
        )
    )
    source = json.dumps(
        {"image_sha256": sha256_file(image), "audio_sha256": sha256_file(audio)},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return MatrixFixture(project.id, root, hashlib.sha256(source).hexdigest())


def _write_wav(path: Path, duration_ms: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frames = 16_000 * duration_ms // 1_000
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(16_000)
        handle.writeframes(b"\0\0" * frames)


def _candidate_identity(candidate: dict[str, object]) -> tuple[str, str]:
    candidate_id = candidate.get("candidate_id")
    source = candidate.get("source")
    if not isinstance(candidate_id, str) or not isinstance(source, dict):
        raise ValueError("validated candidate manifest is incomplete")
    source_commit = source.get("commit")
    if not isinstance(source_commit, str):
        raise ValueError("validated candidate source commit is missing")
    return candidate_id, source_commit


def _case_payload(case: MatrixCaseResult) -> dict[str, object]:
    return {
        "profile": {
            "id": case.profile.id,
            "purpose": case.profile.purpose,
            "width": case.profile.width,
            "height": case.profile.height,
            "fps": case.profile.fps,
        },
        "result": {
            "elapsed_ms": case.elapsed_ms,
            "duration_ms": case.result.duration_ms,
            "width": case.result.width,
            "height": case.result.height,
            "fps": case.result.fps,
            "video_codec": case.result.video_codec,
            "audio_codec": case.result.audio_codec,
            "cached_pages": case.result.cached_pages,
            "final_sha256": case.final_sha256,
            "package_render_config_sha256": case.package_config_sha256,
            "subtitle_present": case.subtitle_present,
            "media_probe": case.media_probe,
        },
    }


def _write_new_json(path: Path, payload: object) -> None:
    if path.exists():
        raise FileExistsError(f"evidence already exists: {path}")
    if not path.parent.is_dir():
        raise FileNotFoundError(f"evidence directory is missing: {path.parent}")
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
