"""Candidate-bound real-media acceptance for DP44 RenderGraph features.

The V1 output matrix exercises page packages.  This module deliberately uses
the packaged Remotion runtime plus the production RenderGraph export pipeline
to prove the independent graph delivery path: dissolve, text overlay, burned
and soft subtitles, and a two-clip FFmpeg audio mix.
"""

from __future__ import annotations

import hashlib
import json
import math
import subprocess
import time
import wave
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID, uuid4

from PIL import Image, ImageChops, ImageDraw, ImageStat

from workbench.rendering.export_pipeline import GraphExportResult, RenderGraphExportPipeline
from workbench.rendering.hashing import sha256_file, sha256_json
from workbench.rendering.models import (
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
from workbench.rendering.remotion_runner import RemotionGraphRunner
from workbench.runtime.layout import RendererRuntime

_SCHEMA_VERSION = "1.0"
_WINDOWS_ACCEPTANCE_PATH_LIMIT = 240
_DURATION_US = 2_000_000
_FPS = 30


@dataclass(frozen=True, slots=True)
class RenderGraphFixture:
    project_id: UUID
    project_root: Path
    graph: RenderGraphV2
    baseline_graph: RenderGraphV2
    source_manifest_sha256: str


@dataclass(frozen=True, slots=True)
class RenderGraphRuntimeResult:
    fixture: RenderGraphFixture
    export: GraphExportResult
    baseline_video: Path
    final_probe: dict[str, object]
    master_audio_probe: dict[str, object]
    burn_overlay_pixel_difference: int
    transition_pixel_difference: int


def execute_render_graph_matrix(
    run_root: Path,
    *,
    runtime: RendererRuntime,
) -> RenderGraphRuntimeResult:
    """Render the DP44 rich graph and a no-feature baseline in a new root."""

    run_root = run_root.resolve()
    if run_root.exists():
        raise FileExistsError(f"RenderGraph matrix run root already exists: {run_root}")
    _require_windows_path_budget(run_root)
    run_root.mkdir(parents=True)
    project_root = run_root / "w"
    project_root.mkdir()
    fixture = _create_fixture(project_root)
    runner = RemotionGraphRunner(project_root, runtime=runtime)
    export = RenderGraphExportPipeline(
        project_root,
        ffmpeg=str(runtime.ffmpeg_executable),
        runner=runner,
    ).export(fixture.graph, run_root / "rich", strict_assets=True)
    baseline_video = run_root / "baseline.mp4"
    runner.render(fixture.baseline_graph, baseline_video, muted=True)
    _require_artifact(baseline_video, "RenderGraph baseline video")

    rich_overlay_frame = run_root / "rich-overlay.png"
    baseline_overlay_frame = run_root / "baseline-overlay.png"
    rich_transition_frame = run_root / "rich-transition.png"
    baseline_transition_frame = run_root / "baseline-transition.png"
    _extract_frame(runtime.ffmpeg_executable, export.video_path, 0.5, rich_overlay_frame)
    _extract_frame(runtime.ffmpeg_executable, baseline_video, 0.5, baseline_overlay_frame)
    _extract_frame(runtime.ffmpeg_executable, export.video_path, 1.0, rich_transition_frame)
    _extract_frame(runtime.ffmpeg_executable, baseline_video, 1.0, baseline_transition_frame)
    burn_overlay_difference = _pixel_difference(rich_overlay_frame, baseline_overlay_frame)
    transition_difference = _pixel_difference(rich_transition_frame, baseline_transition_frame)
    if burn_overlay_difference <= 0:
        raise RuntimeError("DP44 burned subtitle and overlay frame is identical to the baseline")
    if transition_difference <= 0:
        raise RuntimeError("DP44 dissolve transition frame is identical to the baseline")

    final_probe = _probe_media(runtime.ffprobe_executable, export.video_path)
    master_audio_probe = _probe_media(runtime.ffprobe_executable, export.audio_path)
    _require_streams(final_probe, {"video", "audio", "subtitle"})
    _require_streams(master_audio_probe, {"audio"})
    return RenderGraphRuntimeResult(
        fixture=fixture,
        export=export,
        baseline_video=baseline_video,
        final_probe=final_probe,
        master_audio_probe=master_audio_probe,
        burn_overlay_pixel_difference=burn_overlay_difference,
        transition_pixel_difference=transition_difference,
    )


def run_render_graph_matrix_acceptance(
    *,
    repo_root: Path,
    candidate: dict[str, object],
    candidate_manifest_path: Path,
    output_root: Path,
    runtime: RendererRuntime,
) -> Path:
    """Publish append-only, candidate-bound DP44 RenderGraph evidence."""

    repo_root = repo_root.resolve()
    output_root = output_root.resolve()
    _require_test_results_child(repo_root, output_root)
    candidate_id, source_commit = _candidate_identity(candidate)
    manifest_sha256 = sha256_file(candidate_manifest_path)
    run_id = f"r-graph-{time.strftime('%Y%m%dT%H%M%SZ')}-{uuid4().hex[:8]}"
    run_root = _candidate_run_root(output_root, manifest_sha256, run_id)
    report = execute_render_graph_matrix(run_root, runtime=runtime)
    evidence_path = run_root / "render-graph-matrix-acceptance-v1.json"
    payload = {
        "schema_version": _SCHEMA_VERSION,
        "status": "passed",
        "run_id": run_id,
        "candidate": {
            "candidate_id": candidate_id,
            "source_commit": source_commit,
            "manifest_sha256": manifest_sha256,
        },
        "fixture": {
            "id": "DP44-rich-render-graph-v1",
            "duration_us": _DURATION_US,
            "canvas": {"width": 1280, "height": 720, "fps": _FPS},
            "source_manifest_sha256": report.fixture.source_manifest_sha256,
            "content_policy": "generated PNG and generated WAV only",
        },
        "executed": {
            "render_graph_hash": report.export.graph_hash,
            "features": {
                "transition": "dissolve between two overlapping image scenes",
                "overlay": "timed text overlay",
                "burn_in_subtitles": "word-timed English cue rendered by Remotion",
                "soft_subtitles": "ASS/SRT/VTT package with mov_text track in final MP4",
                "audio_mix": "two WAV clips mixed by AudioFilterCompiler",
            },
            "artifacts": {
                "final_video": _artifact(report.export.video_path),
                "video_only": _artifact(_video_only_path(report.export)),
                "master_audio": _artifact(report.export.audio_path),
                "baseline_video": _artifact(report.baseline_video),
                "manifest": _artifact(report.export.manifest_path),
                "subtitles": [_artifact(item.path) for item in report.export.subtitle_artifacts],
            },
            "media_probe": {
                "final": report.final_probe,
                "master_audio": report.master_audio_probe,
            },
            "visual_comparisons": {
                "burn_in_and_overlay_at_0_5s_pixel_difference": (
                    report.burn_overlay_pixel_difference
                ),
                "dissolve_transition_at_1_0s_pixel_difference": report.transition_pixel_difference,
            },
        },
        "runtime": {
            "root": str(runtime.root),
            "node": str(runtime.node_executable),
            "remotion_cli": str(runtime.remotion_cli),
            "browser": str(runtime.browser_executable) if runtime.browser_executable else None,
            "ffmpeg": str(runtime.ffmpeg_executable),
            "ffprobe": str(runtime.ffprobe_executable),
        },
    }
    _write_new_json(evidence_path, payload)
    return evidence_path


def _create_fixture(project_root: Path) -> RenderGraphFixture:
    project_id = uuid4()
    media = project_root / "media"
    media.mkdir()
    first_image = media / "scene-a.png"
    second_image = media / "scene-b.png"
    narration = media / "narration.wav"
    music = media / "music.wav"
    _write_scene(first_image, (34, 82, 152), "Scene A")
    _write_scene(second_image, (160, 65, 76), "Scene B")
    _write_tone(narration, frequency_hz=440.0)
    _write_tone(music, frequency_hz=220.0)
    assets = [
        _asset(project_id, first_image, "image/scene-a.png", "image"),
        _asset(project_id, second_image, "image/scene-b.png", "image"),
        _asset(project_id, narration, "audio/narration.wav", "audio"),
        _asset(project_id, music, "audio/music.wav", "audio"),
    ]
    first = RenderNodeV2(
        kind="image",
        start_us=0,
        end_us=1_250_000,
        source_ref="image/scene-a.png",
        z_index=0,
    )
    second = RenderNodeV2(
        kind="image",
        start_us=750_000,
        end_us=_DURATION_US,
        source_ref="image/scene-b.png",
        z_index=0,
    )
    overlay = RenderNodeV2(
        kind="overlay",
        start_us=250_000,
        end_us=1_750_000,
        source_ref="overlay/dp44-label",
        z_index=100,
        payload={
            "text": "DP44 Overlay",
            "x": 0.06,
            "y": 0.08,
            "width": 0.34,
            "height": 0.1,
            "enter_ms": 150,
            "exit_ms": 150,
        },
    )
    subtitles = SubtitleRenderPlan(
        render_mode="both",
        languages=["en"],
        document_revision=1,
        document_hash="1" * 64,
        cues=[
            SubtitleCue(
                language="en",
                label="English",
                start_us=300_000,
                end_us=900_000,
                text="Rendered subtitle",
                words=[
                    SubtitleWord(text="Rendered", start_us=300_000, end_us=600_000),
                    SubtitleWord(text="subtitle", start_us=600_000, end_us=900_000),
                ],
                style={"font_size": 38, "background_opacity": 0.6},
            ),
            SubtitleCue(
                language="en",
                label="English",
                start_us=1_100_000,
                end_us=1_700_000,
                text="Dissolve transition",
                words=[
                    SubtitleWord(text="Dissolve", start_us=1_100_000, end_us=1_400_000),
                    SubtitleWord(text="transition", start_us=1_400_000, end_us=1_700_000),
                ],
                style={"font_size": 38, "background_opacity": 0.6},
            ),
        ],
    )
    audio = AudioMixPlan(
        clips=[
            AudioMixClip(
                kind="narration",
                source_ref="audio/narration.wav",
                timeline_start_us=0,
                timeline_end_us=_DURATION_US,
                source_in_us=0,
                source_duration_us=_DURATION_US,
                bus="narration",
                gain_db=-4,
            ),
            AudioMixClip(
                kind="music",
                source_ref="audio/music.wav",
                timeline_start_us=0,
                timeline_end_us=_DURATION_US,
                source_in_us=0,
                source_duration_us=_DURATION_US,
                bus="music",
                gain_db=-13,
                fade_in_us=150_000,
                fade_out_us=150_000,
            ),
        ]
    )
    rich = _with_hash(
        RenderGraphV2(
            project_id=project_id,
            timeline_revision=1,
            duration_us=_DURATION_US,
            canvas=GraphCanvas(width=1280, height=720, fps=_FPS, duration_us=_DURATION_US),
            nodes=[first, second, overlay],
            transitions=[
                TransitionEdge(
                    from_node_id=first.id,
                    to_node_id=second.id,
                    kind="dissolve",
                    start_us=750_000,
                    end_us=1_250_000,
                    audio_mode="j_cut",
                    audio_offset_us=-100_000,
                )
            ],
            assets=assets,
            audio=audio,
            subtitles=subtitles,
            graph_hash="0" * 64,
        )
    )
    baseline = _with_hash(
        rich.model_copy(
            update={
                "nodes": [first, second],
                "transitions": [],
                "subtitles": subtitles.model_copy(update={"render_mode": "none", "cues": []}),
                "graph_hash": "0" * 64,
            }
        )
    )
    source = json.dumps(
        {path.name: sha256_file(path) for path in (first_image, second_image, narration, music)},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return RenderGraphFixture(
        project_id=project_id,
        project_root=project_root,
        graph=rich,
        baseline_graph=baseline,
        source_manifest_sha256=hashlib.sha256(source).hexdigest(),
    )


def _asset(project_id: UUID, path: Path, source_ref: str, kind: str) -> ResolvedAsset:
    return ResolvedAsset(
        project_id=project_id,
        kind=kind,
        source_ref=source_ref,
        resolved_path=path.relative_to(path.parents[1]).as_posix(),
        exists=True,
        size_bytes=path.stat().st_size,
        content_hash=sha256_file(path),
        license_status="cleared",
    )


def _with_hash(graph: RenderGraphV2) -> RenderGraphV2:
    payload = graph.model_dump(mode="json", exclude={"graph_hash", "created_at"})
    return graph.model_copy(update={"graph_hash": sha256_json(payload)})


def _write_scene(path: Path, color: tuple[int, int, int], label: str) -> None:
    image = Image.new("RGB", (1280, 720), color)
    draw = ImageDraw.Draw(image)
    draw.rectangle((64, 64, 1216, 656), outline=(255, 255, 255), width=8)
    draw.text((96, 110), label, fill=(255, 255, 255), font_size=64)
    image.save(path, format="PNG")


def _write_tone(path: Path, *, frequency_hz: float) -> None:
    sample_rate = 48_000
    frames = sample_rate * _DURATION_US // 1_000_000
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        values = bytearray()
        for frame in range(frames):
            sample = int(3_000 * math.sin(2 * math.pi * frequency_hz * frame / sample_rate))
            values.extend(sample.to_bytes(2, byteorder="little", signed=True))
        handle.writeframes(values)


def _extract_frame(ffmpeg: Path, video: Path, seconds: float, output: Path) -> None:
    _run_command(
        [
            str(ffmpeg),
            "-y",
            "-loglevel",
            "error",
            "-ss",
            f"{seconds:.3f}",
            "-i",
            str(video),
            "-frames:v",
            "1",
            str(output),
        ],
        "extract RenderGraph validation frame",
    )
    _require_artifact(output, "RenderGraph validation frame")


def _pixel_difference(left: Path, right: Path) -> int:
    with Image.open(left) as left_image, Image.open(right) as right_image:
        difference = ImageChops.difference(left_image.convert("RGB"), right_image.convert("RGB"))
        return round(sum(ImageStat.Stat(difference).sum))


def _probe_media(ffprobe: Path, path: Path) -> dict[str, object]:
    result = subprocess.run(
        [
            str(ffprobe),
            "-v",
            "error",
            "-show_entries",
            "format=duration:stream=codec_type,codec_name,width,height,avg_frame_rate",
            "-of",
            "json",
            str(path),
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or "no ffprobe diagnostics"
        raise RuntimeError(f"RenderGraph ffprobe failed ({result.returncode}): {detail}")
    try:
        parsed = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError("RenderGraph ffprobe did not return JSON") from error
    if not isinstance(parsed, dict):
        raise RuntimeError("RenderGraph ffprobe payload is not an object")
    return parsed


def _require_streams(probe: dict[str, object], expected: set[str]) -> None:
    streams = probe.get("streams")
    if not isinstance(streams, list):
        raise RuntimeError("RenderGraph probe is missing streams")
    observed = {
        stream.get("codec_type")
        for stream in streams
        if isinstance(stream, dict) and isinstance(stream.get("codec_type"), str)
    }
    missing = expected - observed
    if missing:
        message = ", ".join(sorted(missing))
        raise RuntimeError(f"RenderGraph output is missing stream types: {message}")


def _run_command(command: list[str], label: str) -> None:
    result = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or "no process diagnostics"
        raise RuntimeError(f"{label} failed ({result.returncode}): {detail}")


def _candidate_identity(candidate: dict[str, object]) -> tuple[str, str]:
    candidate_id = candidate.get("candidate_id")
    source = candidate.get("source")
    if not isinstance(candidate_id, str) or not isinstance(source, dict):
        raise ValueError("validated candidate manifest is incomplete")
    source_commit = source.get("commit")
    if not isinstance(source_commit, str):
        raise ValueError("validated candidate source commit is missing")
    return candidate_id, source_commit


def _candidate_run_root(output_root: Path, manifest_sha256: str, run_id: str) -> Path:
    if len(manifest_sha256) != 64 or any(
        character not in "0123456789abcdef" for character in manifest_sha256
    ):
        raise ValueError("candidate manifest SHA-256 must be a lowercase 64-character digest")
    if not run_id.startswith("r-graph-"):
        raise ValueError("DP44 RenderGraph run ID is invalid")
    return output_root / f"c-{manifest_sha256[:12]}" / run_id


def _require_windows_path_budget(run_root: Path) -> None:
    projected = run_root / "w" / "media" / "scene-a.png"
    if len(str(projected)) >= _WINDOWS_ACCEPTANCE_PATH_LIMIT:
        raise ValueError(
            "DP44 RenderGraph root is too deep for Windows runtime assets; "
            "choose a shorter path inside test-results"
        )


def _require_test_results_child(repo_root: Path, output_root: Path) -> None:
    allowed_root = (repo_root / "test-results").resolve()
    try:
        output_root.relative_to(allowed_root)
    except ValueError as error:
        raise ValueError("output_root must remain inside repository test-results") from error


def _video_only_path(export: GraphExportResult) -> Path:
    return export.video_path.parent / "video-only.mp4"


def _artifact(path: Path) -> dict[str, object]:
    _require_artifact(path, str(path))
    return {
        "relative_path": path.name,
        "size_bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def _require_artifact(path: Path, label: str) -> None:
    if not path.is_file() or path.stat().st_size <= 0:
        raise RuntimeError(f"{label} is missing or empty: {path}")


def _write_new_json(path: Path, payload: object) -> None:
    if path.exists():
        raise FileExistsError(f"evidence already exists: {path}")
    if not path.parent.is_dir():
        raise FileNotFoundError(f"evidence directory is missing: {path.parent}")
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
