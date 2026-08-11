from __future__ import annotations

from pathlib import Path
from uuid import UUID, uuid4

import pytest
from PIL import Image
from workbench.jobs.execution import RenderCancelled
from workbench.video.models import ProjectVideoProps, SubtitlePlacement, TextRect, VideoPageProps
from workbench.video.process_runner import ProcessCancelled
from workbench.video.render_service import RemotionPageRenderer, RenderError, VideoRenderService


class FakePageRenderer:
    def __init__(self) -> None:
        self.calls: list[int] = []
        self.fail_pages: set[int] = set()

    def render(
        self,
        _: ProjectVideoProps,
        page: VideoPageProps,
        source: Path,
        output: Path,
        control=None,
    ) -> None:
        self.calls.append(page.page_order)
        if page.page_order in self.fail_pages:
            raise RuntimeError(f"page {page.page_order} failed")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(Image.open(source).convert("RGB").tobytes())


def _props(tmp_path: Path, page_count: int = 3) -> ProjectVideoProps:
    pages = []
    for order in range(1, page_count + 1):
        source = tmp_path / f"preview-{order}.png"
        Image.new("RGB", (1920, 1080), (order * 30, 40, 60)).save(source)
        pages.append(
            VideoPageProps(
                page_id=uuid4(),
                page_order=order,
                title=f"第{order}页",
                image_path=source.name,
                audio_path=f"05_音频/page-{order:04d}.wav",
                start_ms=(order - 1) * 1_000,
                end_ms=order * 1_000,
            )
        )
    return ProjectVideoProps(
        project_id=uuid4(),
        duration_ms=page_count * 1_000,
        template_version="tech-board-v1",
        pages=pages,
    )


def _renderer_runtime(tmp_path: Path):
    from workbench.runtime.layout import RendererRuntime

    root = tmp_path / "runtime"
    files = {
        "node/node.exe": "node",
        "remotion/node_modules/@remotion/cli/remotion-cli.js": "cli",
        "remotion/src/index.ts": "entry",
        "ffmpeg/ffmpeg.exe": "ffmpeg",
        "ffmpeg/ffprobe.exe": "ffprobe",
    }
    paths: dict[str, Path] = {}
    for relative_path, contents in files.items():
        path = root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents, encoding="utf-8")
        paths[relative_path] = path
    return RendererRuntime(
        root=root,
        node_executable=paths["node/node.exe"],
        remotion_cli=paths["remotion/node_modules/@remotion/cli/remotion-cli.js"],
        remotion_entry=paths["remotion/src/index.ts"],
        ffmpeg_executable=paths["ffmpeg/ffmpeg.exe"],
        ffprobe_executable=paths["ffmpeg/ffprobe.exe"],
        browser_executable=None,
    )


def test_page_render_cache_skips_unchanged_pages(tmp_path: Path) -> None:
    renderer = FakePageRenderer()
    service = VideoRenderService(tmp_path, renderer)
    props = _props(tmp_path)

    first = service.render_pages(props)
    second = service.render_pages(props)

    assert renderer.calls == [1, 2, 3]
    assert all(item.cached is False for item in first)
    assert all(item.cached is True for item in second)
    assert (tmp_path / "07_视频工程/pages/page-0001.mp4").is_file()


def test_failed_page_can_be_retried_without_rerendering_successful_pages(tmp_path: Path) -> None:
    renderer = FakePageRenderer()
    renderer.fail_pages.add(2)
    service = VideoRenderService(tmp_path, renderer)
    props = _props(tmp_path)

    with pytest.raises(RenderError, match="第2页"):
        service.render_pages(props)

    renderer.fail_pages.clear()
    result = service.render_pages(props)

    assert renderer.calls == [1, 2, 2, 3]
    assert [item.page_order for item in result] == [1, 2, 3]


def test_remotion_renderer_serializes_resolved_page_props_and_uses_frame_range(
    tmp_path: Path,
) -> None:
    props = _props(tmp_path, page_count=1).model_copy(
        update={
            "reduced_motion": True,
            "subtitle_placements": [
                SubtitlePlacement(
                    page_id=UUID("00000000-0000-0000-0000-000000000001"),
                    position="fallback-panel",
                    rect=TextRect(x=96, y=888, width=1_728, height=96),
                    panel=True,
                    reason="fixture",
                )
            ],
        }
    )
    page = props.pages[0]
    props = props.model_copy(
        update={
            "pages": [
                page.model_copy(update={"page_id": UUID("00000000-0000-0000-0000-000000000001")})
            ]
        }
    )
    commands: list[list[str]] = []
    rendered_props: list[str] = []

    def run(command: list[str], _: Path) -> None:
        commands.append(command)
        props_argument = next(item for item in command if item.startswith("--props="))
        rendered_props.append(
            Path(props_argument.removeprefix("--props=")).read_text(encoding="utf-8")
        )
        Path(command[5]).write_bytes(b"remotion-video")

    output = tmp_path / "page.mp4"
    RemotionPageRenderer(tmp_path, runtime=_renderer_runtime(tmp_path), run=run).render(
        props,
        props.pages[0],
        tmp_path / "preview-1.png",
        output,
    )

    assert commands[0][0].endswith("node.exe")
    assert Path(commands[0][1]).as_posix().endswith("@remotion/cli/remotion-cli.js")
    assert "pnpm" not in commands[0]
    assert "render" in commands[0]
    assert "--frames=0-29" in commands[0]
    assert "--timeout=120000" in commands[0]
    serialized = rendered_props[0]
    assert '"reduced_motion": true' in serialized
    assert '"position": "fallback-panel"' in serialized


def test_remotion_renderer_maps_process_cancellation_to_render_cancellation(
    tmp_path: Path,
) -> None:
    class CancellingProcessRunner:
        def run(self, command, cwd, control):
            raise ProcessCancelled("cancelled")

    props = _props(tmp_path, page_count=1)
    renderer = RemotionPageRenderer(
        tmp_path,
        runtime=_renderer_runtime(tmp_path),
        process_runner=CancellingProcessRunner(),
    )

    with pytest.raises(RenderCancelled, match="render process cancelled"):
        renderer.render(
            props,
            props.pages[0],
            tmp_path / "preview-1.png",
            tmp_path / "page.mp4",
        )


def test_remotion_renderer_ceil_frame_count_preserves_short_page_duration(
    tmp_path: Path,
) -> None:
    props = _props(tmp_path, page_count=1).model_copy(
        update={
            "duration_ms": 250,
            "pages": [_props(tmp_path, page_count=1).pages[0].model_copy(update={"end_ms": 250})],
        }
    )
    commands: list[list[str]] = []

    def run(command: list[str], _: Path) -> None:
        commands.append(command)
        Path(command[5]).write_bytes(b"remotion-video")

    RemotionPageRenderer(tmp_path, runtime=_renderer_runtime(tmp_path), run=run).render(
        props,
        props.pages[0],
        tmp_path / "preview-1.png",
        tmp_path / "page.mp4",
    )

    assert "--frames=0-7" in commands[0]


def test_render_pages_reports_progress_and_checks_cancellation(tmp_path: Path) -> None:
    props = _props(tmp_path, page_count=2)
    renderer = FakePageRenderer()
    checkpoints: list[tuple[str, float, str]] = []

    class Context:
        cancel_requested = False

        def checkpoint(self, *, stage, progress, message, artifacts=(), payload=None) -> None:
            checkpoints.append((stage, progress, message))

        def raise_if_cancelled(self) -> None:
            if self.cancel_requested:
                raise RenderCancelled("cancelled")

        def pause_if_requested(self) -> None:
            return None

        def heartbeat(self) -> None:
            return None

    context = Context()
    service = VideoRenderService(tmp_path, renderer)
    result = service.render_pages(props, context=context)

    assert len(result) == 2
    assert [item[0] for item in checkpoints] == ["rendering_pages", "rendering_pages"]
    assert checkpoints[-1][1] == 0.65
