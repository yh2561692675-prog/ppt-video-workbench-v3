from __future__ import annotations

import hashlib
import json
import re
import shutil
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from workbench.domain.enums import NodeStatus
from workbench.domain.issues import PreflightReport
from workbench.domain.models import AuditEvent, ProjectManifest, VideoExportRecord
from workbench.domain.presenter import PresentationMode
from workbench.exports.narration_docx import export_narration_docx
from workbench.jobs.execution import (
    InlineRenderExecutionContext,
    RenderCancelled,
    RenderExecutionContext,
    RenderPauseRequested,
)
from workbench.services.project_service import ProjectService

from .errors import RenderInputChanged, RenderInputStale, RenderJobFailure
from .fingerprint import render_input_fingerprint
from .models import ProjectVideoProps, VideoPreflight
from .preview_service import VideoPreviewService
from .process_runner import (
    CancellableProcessRunner,
    NullProcessControl,
    ProcessCancelled,
    ProcessControl,
    ProcessExecutionError,
)
from .publish import publish_render_outputs
from .render_service import PageRenderer, RenderError, VideoRenderService


class PackageError(ValueError):
    pass


class PackageArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    relative_path: str
    size: int = Field(ge=0)
    sha256: str = Field(min_length=64, max_length=64)


class PackageManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = 1
    artifacts: list[PackageArtifact] = Field(min_length=1)


class VideoExportBlocked(RuntimeError):
    pass


class VideoExportError(RuntimeError):
    pass


class VideoExportResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mp4_relative_path: str
    package_relative_path: str
    duration_ms: int = Field(ge=0)
    width: int = 1920
    height: int = 1080
    fps: int = 30
    video_codec: str
    audio_codec: str
    artifact_count: int = Field(ge=1)
    cached_pages: int = Field(ge=0)


MEDIA_DURATION_TOLERANCE_MS = 100


def _with_export_profile(
    preflight: VideoPreflight, props_override: ProjectVideoProps | None
) -> VideoPreflight:
    """Keep the queue-frozen output profile inside the render fingerprint.

    The project preflight deliberately describes source material.  A queued
    delivery profile is immutable job input, so it is substituted only after
    the normal preflight has succeeded and before all fingerprint checks.
    """

    if props_override is None:
        return preflight
    if preflight.props is None:
        raise VideoExportBlocked("video export profile cannot replace missing preflight props")
    source = preflight.props.model_dump(mode="json", exclude={"width", "height", "fps"})
    override = props_override.model_dump(mode="json", exclude={"width", "height", "fps"})
    if source != override:
        raise VideoExportBlocked("video export profile changed source inputs after preflight")
    return preflight.model_copy(update={"props": props_override})


def build_page_mux_command(
    ffmpeg: str,
    rendered_page: Path,
    audio: Path,
    output: Path,
    *,
    start_ms: int,
    end_ms: int,
    seek_master_audio: bool,
) -> list[str]:
    inputs = [ffmpeg, "-y", "-loglevel", "error", "-i", str(rendered_page)]
    if seek_master_audio:
        inputs.extend(["-ss", f"{start_ms / 1_000:.3f}"])
    inputs.extend(["-i", str(audio)])
    return [
        *inputs,
        "-t",
        f"{(end_ms - start_ms) / 1_000:.3f}",
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-shortest",
        str(output),
    ]


def build_final_concat_command(
    ffmpeg: str,
    concat_file: Path,
    output: Path,
    *,
    duration_ms: int,
    fps: int,
) -> list[str]:
    """Join page segments while preserving the frozen constant frame rate.

    Page muxing produces H.264/AAC fragments.  Stream-copying those fragments
    through the concat demuxer lets AAC packet padding alter the video stream
    time base (for example 48000/1001 after two nominal 24fps pages).  The
    final delivery must be CFR, so perform the one required final video/audio
    encode at the project profile instead of copying the concatenated streams.
    """

    return [
        ffmpeg,
        "-y",
        "-loglevel",
        "error",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(concat_file),
        "-t",
        f"{duration_ms / 1_000:.3f}",
        "-map",
        "0:v:0",
        "-map",
        "0:a:0",
        "-vf",
        f"fps={fps},format=yuv420p",
        "-r",
        str(fps),
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        str(output),
    ]


class VideoExportService:
    def __init__(
        self,
        projects: ProjectService,
        preview: VideoPreviewService,
        ffmpeg: str = "ffmpeg",
        ffprobe: str = "ffprobe",
        renderer: PageRenderer | None = None,
        preflight_gate: Callable[[UUID], PreflightReport] | None = None,
        process_runner: CancellableProcessRunner | None = None,
    ) -> None:
        self.projects = projects
        self.preview = preview
        self.ffmpeg = ffmpeg
        self.ffprobe = ffprobe
        self.renderer = renderer
        self.preflight_gate = preflight_gate
        self.process_runner = process_runner or CancellableProcessRunner()

    def mark_failed(self, project_id: UUID, *, error_code: str) -> None:
        project = self.projects.get(project_id)
        now = datetime.now(UTC)
        self.projects.save(
            project.model_copy(
                update={
                    "video_export": VideoExportRecord(
                        id=uuid4(),
                        status=NodeStatus.FAILED,
                        duration_ms=0,
                        artifact_count=0,
                        error_code=error_code,
                        exported_at=now,
                    ),
                    "audit_log": [
                        *project.audit_log,
                        AuditEvent(
                            action="video_export_failed",
                            occurred_at=now,
                            details={"error_code": error_code},
                        ),
                    ],
                }
            )
        )

    def export(
        self,
        project_id: UUID,
        *,
        context: RenderExecutionContext | None = None,
        props_override: ProjectVideoProps | None = None,
    ) -> VideoExportResult:
        project = self.projects.get(project_id)
        execution: RenderExecutionContext = context or InlineRenderExecutionContext()
        try:
            if self.preflight_gate is not None:
                report = self.preflight_gate(project_id)
                if not report.allowed:
                    raise VideoExportBlocked("当前项目预检尚未通过")
            return self._export(project_id, project, execution, props_override=props_override)
        except VideoExportBlocked:
            raise
        except (RenderCancelled, RenderPauseRequested):
            raise
        except RenderJobFailure:
            raise
        except (VideoExportError, RenderError, PackageError):
            if execution.job_id is None:
                self.mark_failed(project_id, error_code="video_export_rejected")
            raise
        except Exception as error:
            if execution.job_id is None:
                self.mark_failed(project_id, error_code="video_export_rejected")
            raise VideoExportError("视频导出失败，请检查渲染环境和制作素材") from error

    def _export(
        self,
        project_id: UUID,
        project: ProjectManifest,
        context: RenderExecutionContext | None = None,
        *,
        props_override: ProjectVideoProps | None = None,
    ) -> VideoExportResult:
        execution: RenderExecutionContext = context or InlineRenderExecutionContext()
        preflight = self.preview.preflight(project_id)
        if not preflight.allowed or preflight.props is None:
            raise VideoExportBlocked("视频完整预检尚未通过")
        effective_preflight = _with_export_profile(preflight, props_override)
        if (
            execution.input_fingerprint is not None
            and render_input_fingerprint(effective_preflight) != execution.input_fingerprint
        ):
            raise RenderInputStale("渲染输入已在任务入队后发生变化")
        props = effective_preflight.props
        if props is None:
            raise VideoExportBlocked("video export profile is missing")
        root = (self.projects.workspace_root / project.project_dir).resolve()
        run_id = str(execution.job_id or uuid4())
        output_dir = root / "08_输出"
        staging_root = output_dir / ".render-jobs" / run_id
        staging_root.mkdir(parents=True, exist_ok=True)
        execution.register_temporary_paths((staging_root,))
        rendered = VideoRenderService(
            root,
            self.renderer,
            output_dir=staging_root / "pages",
        ).render_pages(props, context=execution)
        segments_dir = staging_root / "segments"
        segments_dir.mkdir(parents=True, exist_ok=True)
        segments = []
        human_mode = project.presentation_mode is PresentationMode.HUMAN_PRESENTER
        for page, rendered_page in zip(props.pages, rendered, strict=True):
            execution.raise_if_cancelled()
            segment = segments_dir / f"page-{page.page_order:04d}.mp4"
            audio = self._safe_path(root, page.audio_path)
            if not audio.is_file():
                raise VideoExportError(f"第{page.page_order}页音频文件不存在")
            self._run_ffmpeg(
                build_page_mux_command(
                    self.ffmpeg,
                    rendered_page.path,
                    audio,
                    segment,
                    start_ms=page.start_ms,
                    end_ms=page.end_ms,
                    seek_master_audio=human_mode,
                ),
                root,
                execution,
            )
            validate_media_probe(
                self._probe(segment, execution),
                expected_duration_ms=page.end_ms - page.start_ms,
                tolerance_ms=MEDIA_DURATION_TOLERANCE_MS,
                expected_width=props.width,
                expected_height=props.height,
                expected_fps=props.fps,
            )
            segments.append(segment)

        output_dir.mkdir(parents=True, exist_ok=True)
        final_mp4 = staging_root / "最终视频.mp4"
        concat_file = segments_dir / "concat.txt"
        concat_file.write_text(
            "".join(f"file '{segment.name}'\n" for segment in segments), encoding="utf-8"
        )
        execution.checkpoint(stage="muxing", progress=0.70, message="开始合成视频")
        self._run_ffmpeg(
            build_final_concat_command(
                self.ffmpeg,
                concat_file,
                final_mp4,
                duration_ms=props.duration_ms,
                fps=props.fps,
            ),
            segments_dir,
            execution,
        )
        probe = self._probe(final_mp4, execution)
        validate_media_probe(
            probe,
            expected_duration_ms=props.duration_ms,
            tolerance_ms=max(MEDIA_DURATION_TOLERANCE_MS, 150),
            expected_width=props.width,
            expected_height=props.height,
            expected_fps=props.fps,
        )
        measured_duration_ms = probe.get("duration_ms")
        if not isinstance(measured_duration_ms, int):
            raise VideoExportError("成片时长无法读取")

        execution.checkpoint(stage="packaging", progress=0.82, message="开始制作交付包")
        package = staging_root / "制作包"
        package.mkdir(parents=True, exist_ok=True)
        shutil.copy2(final_mp4, package / "最终视频.mp4")
        srt = root / "06_字幕" / "字幕.srt"
        if not srt.is_file():
            raise VideoExportError("缺少字幕 SRT")
        shutil.copy2(srt, package / "字幕.srt")
        if human_mode:
            if project.presenter_source is None:
                raise VideoExportError("真人模式缺少讲解视频源")
            presenter_dir = package / "presenter"
            presenter_dir.mkdir(parents=True, exist_ok=True)
            source = self._safe_path(root, project.presenter_source.relative_path)
            shutil.copy2(source, presenter_dir / f"source{source.suffix.lower()}")
            presenter_artifacts = root / "03_文字识别" / "presenter"
            for name in ("transcript.json", "matches.json", "timeline.json"):
                artifact = presenter_artifacts / name
                if not artifact.is_file():
                    raise VideoExportError(f"真人模式缺少分析产物：{name}")
                shutil.copy2(artifact, presenter_dir / name)
            if props.presenter_timeline is None or props.timeline_hash is None:
                raise VideoExportError("真人模式缺少可交付的时间轴哈希")
            (presenter_dir / "window-plan.json").write_text(
                json.dumps(
                    {
                        "schema_version": props.presenter_timeline.schema_version,
                        "timeline_revision": props.timeline_revision,
                        "timeline_hash": props.timeline_hash,
                        "segments": [
                            item.model_dump(mode="json")
                            for item in props.presenter_timeline.segments
                        ],
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
        else:
            narration = export_narration_docx(project, root)
            shutil.copy2(narration, package / "旁白确认版.docx")
            audio_dir = package / "分页音频"
            audio_dir.mkdir(parents=True, exist_ok=True)
            for page in props.pages:
                audio = self._safe_path(root, page.audio_path)
                shutil.copy2(audio, audio_dir / f"page-{page.page_order:04d}.wav")
        remotion_dir = package / "Remotion工程"
        remotion_dir.mkdir(parents=True, exist_ok=True)
        (remotion_dir / "ProjectVideoProps.json").write_text(
            props.model_dump_json(indent=2) + "\n", encoding="utf-8"
        )
        effect_plans_dir = remotion_dir / "effect-plans"
        effect_plans_dir.mkdir(parents=True, exist_ok=True)
        for page in props.pages:
            if page.effect_plan is not None:
                (effect_plans_dir / f"page-{page.page_order:04d}.json").write_text(
                    json.dumps(
                        {
                            "page_id": str(page.page_id),
                            "revision": page.effect_plan_revision,
                            "plan_hash": page.effect_plan_hash,
                            "plan": page.effect_plan.model_dump(mode="json"),
                        },
                        ensure_ascii=False,
                        indent=2,
                    )
                    + "\n",
                    encoding="utf-8",
                )
        (remotion_dir / "EffectCatalog.json").write_text(
            json.dumps(
                {
                    "catalog_version": props.catalog_version,
                    "template_version": props.template_version,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        (package / "预检报告.json").write_text(
            preflight.model_dump_json(indent=2) + "\n", encoding="utf-8"
        )
        (package / "日志清单.json").write_text(
            json.dumps(
                {"events": ["page_rendered", "ffmpeg_composed", "package_validated"]},
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        (package / "render.config.json").write_text(
            json.dumps(
                {"width": props.width, "height": props.height, "fps": props.fps},
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        artifact_paths = sorted(
            (path for path in package.rglob("*") if path.is_file()),
            key=lambda path: path.relative_to(package).as_posix(),
        )
        manifest = build_package_manifest(package, artifact_paths)
        (package / "制作包清单.json").write_text(
            manifest.model_dump_json(indent=2) + "\n", encoding="utf-8"
        )
        execution.checkpoint(stage="publishing", progress=0.94, message="发布渲染产物")
        execution.raise_if_cancelled()
        latest_preflight = self.preview.preflight(project_id)
        if not latest_preflight.allowed or latest_preflight.props is None:
            raise RenderInputChanged("发布前预检已失效")
        latest_effective_preflight = _with_export_profile(latest_preflight, props_override)
        if (
            execution.input_fingerprint is not None
            and render_input_fingerprint(latest_effective_preflight)
            != execution.input_fingerprint
        ):
            raise RenderInputChanged("渲染期间项目输入发生变化")
        published = publish_render_outputs(
            staging_root=staging_root,
            output_root=output_dir,
            run_id=run_id,
            final_name=final_mp4.name,
            package_name=package.name,
        )
        result = VideoExportResult(
            mp4_relative_path="08_输出/最终视频.mp4",
            package_relative_path="08_输出/制作包",
            duration_ms=measured_duration_ms,
            width=props.width,
            height=props.height,
            fps=props.fps,
            video_codec="h264",
            audio_codec="aac",
            artifact_count=len(manifest.artifacts) + 1,
            cached_pages=sum(item.cached for item in rendered),
        )
        result = result.model_copy(
            update={
                "mp4_relative_path": published.mp4_path.relative_to(root).as_posix(),
                "package_relative_path": published.package_path.relative_to(root).as_posix(),
            }
        )
        execution.checkpoint(stage="completed", progress=1.0, message="渲染完成")
        latest = self.projects.get(project_id)
        self.projects.save(
            latest.model_copy(
                update={
                    "video_export": VideoExportRecord(
                        id=uuid4(),
                        status=NodeStatus.COMPLETED,
                        mp4_relative_path=result.mp4_relative_path,
                        package_relative_path=result.package_relative_path,
                        duration_ms=result.duration_ms,
                        artifact_count=result.artifact_count,
                        exported_at=datetime.now(UTC),
                    )
                }
            )
        )
        return result

    def _run_ffmpeg(
        self, command: list[str], cwd: Path, control: ProcessControl | None = None
    ) -> None:
        try:
            self.process_runner.run(command, cwd, control or NullProcessControl())
        except ProcessCancelled:
            raise
        except ProcessExecutionError as error:
            raise VideoExportError("FFmpeg 合成失败，请检查视频日志") from error

    def _probe(self, path: Path, control: ProcessControl | None = None) -> dict[str, object]:
        try:
            completed = self.process_runner.run(
                [
                    self.ffprobe,
                    "-v",
                    "error",
                    "-show_streams",
                    "-show_format",
                    "-of",
                    "json",
                    str(path),
                ],
                path.parent,
                control or NullProcessControl(),
            )
        except ProcessCancelled:
            raise
        except ProcessExecutionError as error:
            fallback = self._probe_with_ffmpeg(path, control)
            if fallback is not None:
                return fallback
            raise VideoExportError("无法校验最终视频") from error
        payload = json.loads(completed.stdout)
        streams: list[dict[str, object]] = payload.get("streams", [])
        format_data = payload.get("format", {})
        video: dict[str, object] = next(
            (item for item in streams if item.get("width") is not None), {}
        )
        audio: dict[str, object] = next(
            (item for item in streams if item.get("codec_name") == "aac"), {}
        )
        return {
            "width": video.get("width"),
            "height": video.get("height"),
            "fps": _probe_fps(video),
            "video_codec": video.get("codec_name"),
            "audio_codec": audio.get("codec_name"),
            "duration_ms": round(float(format_data.get("duration", 0)) * 1_000),
        }

    def _probe_with_ffmpeg(
        self, path: Path, control: ProcessControl | None = None
    ) -> dict[str, object] | None:
        try:
            completed = self.process_runner.run(
                [self.ffmpeg, "-hide_banner", "-i", str(path)],
                path.parent,
                control or NullProcessControl(),
            )
        except ProcessCancelled:
            raise
        except ProcessExecutionError as error:
            if error.result is None:
                return None
            completed = error.result
        output = f"{completed.stdout}\n{completed.stderr}"
        duration = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", output)
        video = re.search(r"Video:\s*([^,\s]+).*?(\d{2,5})x(\d{2,5})", output)
        # FFmpeg prints a measured average frame rate before the nominal
        # stream time base (for example ``29.05 fps, 30 tbr`` when container
        # duration includes audio padding).  V1 exports are CFR, so validate
        # the declared stream rate first and only fall back to the average
        # when a tool omits tbr.
        fps = re.search(r"(\d+(?:\.\d+)?)\s+tbr", output) or re.search(
            r"(\d+(?:\.\d+)?)\s+fps", output
        )
        audio = re.search(r"Audio:\s*([^,\s]+)", output)
        if duration is None or video is None or audio is None or fps is None:
            return None
        hours, minutes, seconds = duration.groups()
        duration_ms = round((int(hours) * 3600 + int(minutes) * 60 + float(seconds)) * 1_000)
        return {
            "width": int(video.group(2)),
            "height": int(video.group(3)),
            "fps": round(float(fps.group(1))),
            "video_codec": video.group(1),
            "audio_codec": audio.group(1),
            "duration_ms": duration_ms,
        }

    @staticmethod
    def _safe_path(root: Path, relative_path: str) -> Path:
        target = (root / relative_path).resolve()
        if root not in target.parents:
            raise VideoExportError("视频资源路径超出项目目录")
        return target


def build_package_manifest(root: Path, paths: list[Path]) -> PackageManifest:
    package_root = root.resolve()
    artifacts: list[PackageArtifact] = []
    for path in paths:
        target = path.resolve()
        if package_root not in target.parents:
            raise PackageError(f"文件超出制作包目录：{path}")
        if not target.is_file():
            raise PackageError(f"缺少制作包文件：{path}")
        artifacts.append(
            PackageArtifact(
                relative_path=target.relative_to(package_root).as_posix(),
                size=target.stat().st_size,
                sha256=_sha256(target),
            )
        )
    if not artifacts:
        raise PackageError("制作包没有可交付文件")
    return PackageManifest(artifacts=artifacts)


def validate_media_probe(
    probe: dict[str, object],
    *,
    expected_duration_ms: int,
    tolerance_ms: int,
    expected_width: int = 1920,
    expected_height: int = 1080,
    expected_fps: int = 30,
) -> None:
    expected = {
        "width": expected_width,
        "height": expected_height,
        "fps": expected_fps,
        "video_codec": "h264",
        "audio_codec": "aac",
    }
    observed = {key: probe.get(key) for key in expected}
    if observed != expected:
        raise VideoExportError(f"成片编码或画布不符合契约：{observed}")
    duration_ms = probe.get("duration_ms")
    if not isinstance(duration_ms, int) or abs(duration_ms - expected_duration_ms) > tolerance_ms:
        raise VideoExportError(
            f"成片时长不符合契约：实际 {duration_ms}ms，预期 {expected_duration_ms}ms"
        )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _probe_fps(video: dict[str, object]) -> int | None:
    """Normalize ffprobe's rational frame rate without accepting malformed data."""

    raw = video.get("avg_frame_rate") or video.get("r_frame_rate")
    if not isinstance(raw, str) or "/" not in raw:
        return None
    numerator, denominator = raw.split("/", maxsplit=1)
    try:
        value = int(numerator) / int(denominator)
    except (ValueError, ZeroDivisionError):
        return None
    return round(value)
