from __future__ import annotations

import hashlib
import inspect
import json
import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from PIL import Image

from workbench.jobs.execution import (
    InlineRenderExecutionContext,
    RenderCancelled,
    RenderExecutionContext,
    RenderPauseRequested,
)
from workbench.runtime.layout import RendererRuntime, RuntimeLayout

from .models import ProjectVideoProps, VideoPageProps
from .process_runner import (
    CancellableProcessRunner,
    NullProcessControl,
    ProcessCancelled,
    ProcessControl,
    ProcessExecutionError,
)


class PageRenderer(Protocol):
    def render(
        self,
        props: ProjectVideoProps,
        page: VideoPageProps,
        source: Path,
        output: Path,
        control: ProcessControl | None = None,
    ) -> None: ...


class RenderError(RuntimeError):
    pass


REMOTION_TIMEOUT_MS = 120_000


@dataclass(frozen=True)
class RenderedPage:
    page_order: int
    path: Path
    cache_key: str
    cached: bool


class PillowPageRenderer:
    def render(
        self,
        props: ProjectVideoProps,
        __: VideoPageProps,
        source: Path,
        output: Path,
        control: ProcessControl | None = None,
    ) -> None:
        with Image.open(source) as opened:
            image = opened.convert("RGB")
            image.thumbnail((props.width, props.height), Image.Resampling.LANCZOS)
            canvas = Image.new("RGB", (props.width, props.height), (7, 17, 31))
            left = (props.width - image.width) // 2
            top = (props.height - image.height) // 2
            canvas.paste(image, (left, top))
            output.parent.mkdir(parents=True, exist_ok=True)
            canvas.save(output, format="PNG", optimize=True)


class RemotionPageRenderer:
    def __init__(
        self,
        project_root: Path,
        *,
        remotion_root: Path | None = None,
        runtime: RendererRuntime | None = None,
        browser_executable: str | None = None,
        run: Callable[[list[str], Path], None] | None = None,
        process_runner: CancellableProcessRunner | None = None,
    ) -> None:
        self.project_root = project_root.resolve()
        self.runtime = runtime or RuntimeLayout.from_environment().require_renderer()
        self.remotion_root = (remotion_root or self.runtime.root / "remotion").resolve()
        self.browser_executable = browser_executable or (
            str(self.runtime.browser_executable) if self.runtime.browser_executable else None
        )
        self.run = run
        self.process_runner = process_runner or CancellableProcessRunner()

    def render(
        self,
        props: ProjectVideoProps,
        page: VideoPageProps,
        _: Path,
        output: Path,
        control: ProcessControl | None = None,
    ) -> None:
        output.parent.mkdir(parents=True, exist_ok=True)
        props_path = output.with_name(f".{output.stem}.props.json")
        render_props = props
        frame_duration_ms = (1_000 + props.fps - 1) // props.fps
        minimum_duration_ms = page.end_ms + frame_duration_ms
        if minimum_duration_ms > props.duration_ms:
            render_props = props.model_copy(update={"duration_ms": minimum_duration_ms})
        props_path.write_text(
            json.dumps({"props": render_props.model_dump(mode="json")}, ensure_ascii=False),
            encoding="utf-8",
        )
        start_frame = (page.start_ms * props.fps + 500) // 1_000
        duration_frames = max(
            1,
            ((page.end_ms - page.start_ms) * props.fps + 999) // 1_000,
        )
        end_frame = start_frame + duration_frames - 1
        command = [
            str(self.runtime.node_executable),
            str(self.runtime.remotion_cli),
            "render",
            str(self.runtime.remotion_entry),
            "PptVideoWorkbench",
            str(output),
            f"--props={props_path}",
            f"--frames={start_frame}-{end_frame}",
            f"--public-dir={self.project_root}",
            "--codec=h264",
            "--muted",
            "--concurrency=1",
            f"--timeout={REMOTION_TIMEOUT_MS}",
            "--log=error",
        ]
        if self.browser_executable:
            command.append(f"--browser-executable={self.browser_executable}")
            command.append("--chrome-mode=chrome-for-testing")
        try:
            if self.run is not None:
                self.run(command, self.remotion_root)
            else:
                self._run(command, self.remotion_root, control or NullProcessControl())
        finally:
            props_path.unlink(missing_ok=True)

    def _run(self, command: list[str], cwd: Path, control: ProcessControl) -> None:
        try:
            self.process_runner.run(command, cwd, control)
        except ProcessCancelled as error:
            raise RenderCancelled("render process cancelled") from error
        except ProcessExecutionError as error:
            raise RenderError("Remotion 页面渲染失败") from error


class VideoRenderService:
    def __init__(
        self,
        project_root: Path,
        renderer: PageRenderer | None = None,
        *,
        output_dir: Path | None = None,
    ) -> None:
        self.project_root = project_root.resolve()
        self.renderer = renderer or RemotionPageRenderer(self.project_root)
        self.cache_path = self.project_root / "07_视频工程" / "page-cache.json"
        self.output_dir = (output_dir or self.project_root / "07_视频工程" / "pages").resolve()

    def render_pages(
        self,
        props: ProjectVideoProps,
        *,
        context: RenderExecutionContext | None = None,
    ) -> list[RenderedPage]:
        execution = context or InlineRenderExecutionContext()
        cache = self._read_cache()
        results: list[RenderedPage] = []
        total_pages = max(len(props.pages), 1)
        for page in props.pages:
            execution.raise_if_cancelled()
            source = self._safe_path(page.image_path)
            if not source.is_file():
                raise RenderError(f"第{page.page_order}页预览图不存在")
            output = self.output_dir / f"page-{page.page_order:04d}.mp4"
            cache_key = self._cache_key(props, page, source)
            record = cache.get(str(page.page_order))
            if (
                isinstance(record, dict)
                and record.get("cache_key") == cache_key
                and output.is_file()
            ):
                results.append(RenderedPage(page.page_order, output, cache_key, True))
                execution.checkpoint(
                    stage="rendering_pages",
                    progress=0.05 + 0.60 * len(results) / total_pages,
                    message=f"第 {page.page_order} 页缓存命中",
                    artifacts=(output,),
                    payload={
                        "completed_pages": [item.page_order for item in results],
                        "cached": True,
                    },
                )
                execution.pause_if_requested()
                continue
            try:
                temporary = output.with_name(f".{output.stem}.tmp.mp4")
                render_signature = inspect.signature(self.renderer.render)
                if "control" in render_signature.parameters:
                    self.renderer.render(props, page, source, temporary, control=execution)
                else:
                    self.renderer.render(props, page, source, temporary)
                if not temporary.is_file() or temporary.stat().st_size == 0:
                    raise RenderError("页面渲染结果为空")
                os.replace(temporary, output)
            except (RenderCancelled, RenderPauseRequested):
                temporary.unlink(missing_ok=True)
                raise
            except Exception as error:
                temporary.unlink(missing_ok=True)
                if isinstance(error, RenderError):
                    raise RenderError(f"第{page.page_order}页渲染失败：{error}") from error
                raise RenderError(f"第{page.page_order}页渲染失败：{error}") from error
            cache[str(page.page_order)] = {
                "cache_key": cache_key,
                "relative_path": str(output.relative_to(self.project_root)),
            }
            self._write_cache(cache)
            results.append(RenderedPage(page.page_order, output, cache_key, False))
            execution.checkpoint(
                stage="rendering_pages",
                progress=0.05 + 0.60 * len(results) / total_pages,
                message=f"第 {page.page_order} 页渲染完成",
                artifacts=(output,),
                payload={"completed_pages": [item.page_order for item in results], "cached": False},
            )
            execution.pause_if_requested()
        return results

    def _safe_path(self, relative_path: str) -> Path:
        target = (self.project_root / relative_path).resolve()
        if self.project_root not in target.parents:
            raise RenderError("页面预览图路径超出项目目录")
        return target

    def _cache_key(self, props: ProjectVideoProps, page: VideoPageProps, source: Path) -> str:
        digest = hashlib.sha256()
        digest.update(props.template_version.encode("utf-8"))
        digest.update(
            json.dumps(
                {
                    "page": page.model_dump(mode="json"),
                    "effect_plan_hash": page.effect_plan_hash,
                    "catalog_version": props.catalog_version,
                    "width": props.width,
                    "height": props.height,
                    "fps": props.fps,
                    "subtitles": [
                        cue.model_dump(mode="json")
                        for cue in props.subtitles
                        if cue.page_id == page.page_id
                    ],
                    "placement": next(
                        (
                            placement.model_dump(mode="json")
                            for placement in props.subtitle_placements
                            if placement.page_id == page.page_id
                        ),
                        None,
                    ),
                    "reduced_motion": props.reduced_motion,
                },
                ensure_ascii=False,
                sort_keys=True,
            ).encode("utf-8")
        )
        digest.update(hashlib.sha256(source.read_bytes()).digest())
        return digest.hexdigest()

    def _read_cache(self) -> dict[str, object]:
        if not self.cache_path.is_file():
            return {}
        try:
            payload = json.loads(self.cache_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return payload if isinstance(payload, dict) else {}

    def _write_cache(self, cache: dict[str, object]) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.cache_path.with_name(f".{self.cache_path.name}.tmp")
        temporary.write_text(
            json.dumps(cache, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, self.cache_path)
