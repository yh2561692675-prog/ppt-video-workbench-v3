from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from workbench.jobs.execution import RenderExecutionContext
from workbench.video.process_runner import (
    CancellableProcessRunner,
    NullProcessControl,
    ProcessControl,
)

from .ffmpeg_audio import AudioFilterCompiler, build_audio_render_command
from .final_mux import build_final_mux_command
from .hashing import sha256_file
from .models import RenderGraphV2
from .preflight import GraphPreflight, GraphPreflightReport
from .remotion_runner import RemotionGraphRunner
from .subtitle_packager import SubtitleArtifact, SubtitlePackager


class GraphExportBlocked(RuntimeError):
    def __init__(self, report: GraphPreflightReport) -> None:
        super().__init__("RenderGraph V2 导出预检未通过")
        self.report = report


class GraphExportError(RuntimeError):
    pass


@dataclass(frozen=True)
class GraphExportResult:
    graph_hash: str
    video_path: Path
    audio_path: Path
    subtitle_artifacts: tuple[SubtitleArtifact, ...]
    manifest_path: Path


class RenderGraphExportPipeline:
    """Execute the full graph: preflight -> Remotion -> FFmpeg -> package."""

    def __init__(
        self,
        project_root: Path,
        *,
        ffmpeg: str = "ffmpeg",
        runner: RemotionGraphRunner | None = None,
        process_runner: CancellableProcessRunner | None = None,
        run: object | None = None,
    ) -> None:
        self.project_root = project_root.resolve()
        self.ffmpeg = ffmpeg
        # The packaged Remotion runtime is only required when an export actually
        # renders video.  Keeping the default runner lazy lets callers exercise
        # the independently injectable FFmpeg process path in source checkouts.
        self.runner = runner
        self.process_runner = process_runner or CancellableProcessRunner()
        self.run = run

    def export(
        self,
        graph: RenderGraphV2,
        output_dir: Path,
        *,
        context: RenderExecutionContext | None = None,
        strict_assets: bool = True,
    ) -> GraphExportResult:
        report = GraphPreflight().check(
            graph,
            self.project_root,
            strict_assets=strict_assets,
        )
        if not report.allowed:
            raise GraphExportBlocked(report)
        execution = context or NullProcessControl()
        output_dir = output_dir.resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        video_only = output_dir / "video-only.mp4"
        master_audio = output_dir / "master.wav"
        final_video = output_dir / "最终视频.mp4"
        subtitles_dir = output_dir / "subtitles"
        runner = self.runner or RemotionGraphRunner(self.project_root)
        runner.render(graph, video_only, control=execution, muted=True)
        self._require_artifact(video_only, "Remotion video-only 输出")
        self._run_ffmpeg(
            build_audio_render_command(
                self.ffmpeg,
                AudioFilterCompiler().compile(graph, self.project_root),
                master_audio,
            ),
            output_dir,
            execution,
        )
        self._require_artifact(master_audio, "FFmpeg master audio 输出")
        subtitle_artifacts = SubtitlePackager().write(graph.subtitles, subtitles_dir)
        soft_tracks = (
            [artifact for artifact in subtitle_artifacts if artifact.format == "ass"]
            if graph.subtitles.render_mode in {"soft", "both"}
            else []
        )
        self._run_ffmpeg(
            build_final_mux_command(
                self.ffmpeg,
                video_only,
                master_audio,
                final_video,
                subtitles=soft_tracks,
            ),
            output_dir,
            execution,
        )
        self._require_artifact(final_video, "FFmpeg final mux 输出")
        manifest = output_dir / "render-manifest.json"
        manifest.write_text(
            json.dumps(
                {
                    "schema_version": "1.0",
                    "graph_hash": graph.graph_hash,
                    "timeline_revision": graph.timeline_revision,
                    "video_only": video_only.name,
                    "master_audio": master_audio.name,
                    "final_video": final_video.name,
                    "subtitles": [
                        artifact.path.relative_to(output_dir).as_posix()
                        for artifact in subtitle_artifacts
                    ],
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        package_manifest = output_dir / "制作包清单.json"
        artifacts = []
        for path in sorted(output_dir.rglob("*")):
            if not path.is_file() or path == package_manifest:
                continue
            artifacts.append(
                {
                    "relative_path": path.relative_to(output_dir).as_posix(),
                    "size": path.stat().st_size,
                    "sha256": sha256_file(path),
                }
            )
        package_manifest.write_text(
            json.dumps(
                {"version": 1, "artifacts": artifacts},
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return GraphExportResult(
            graph_hash=graph.graph_hash,
            video_path=final_video,
            audio_path=master_audio,
            subtitle_artifacts=tuple(subtitle_artifacts),
            manifest_path=manifest,
        )

    def _run_ffmpeg(
        self,
        command: list[str],
        cwd: Path,
        control: ProcessControl,
    ) -> None:
        if self.run is not None:
            callback = self.run
            if not callable(callback):
                raise GraphExportError("FFmpeg runner is not callable")
            callback(command, cwd)
            return
        self.process_runner.run(command, cwd, control)

    @staticmethod
    def _require_artifact(path: Path, label: str) -> None:
        try:
            valid = path.is_file() and path.stat().st_size > 0
        except OSError as error:
            raise GraphExportError(f"{label} 无法读取: {path}") from error
        if not valid:
            raise GraphExportError(f"{label} 缺失或为空: {path}")
