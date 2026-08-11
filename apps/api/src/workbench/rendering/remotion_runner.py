from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

from workbench.jobs.execution import RenderCancelled
from workbench.runtime.layout import RendererRuntime, RuntimeLayout
from workbench.video.process_runner import (
    CancellableProcessRunner,
    NullProcessControl,
    ProcessCancelled,
    ProcessControl,
    ProcessExecutionError,
)

from .models import RenderGraphV2
from .timebase import duration_to_frames


class GraphRenderError(RuntimeError):
    pass


class RemotionGraphRunner:
    """Render one immutable graph as a single full-duration composition."""

    timeout_ms = 120_000

    def __init__(
        self,
        project_root: Path,
        *,
        runtime: RendererRuntime | None = None,
        browser_executable: str | None = None,
        run: Callable[[list[str], Path], None] | None = None,
        process_runner: CancellableProcessRunner | None = None,
    ) -> None:
        self.project_root = project_root.resolve()
        self.runtime = runtime or RuntimeLayout.from_environment().require_renderer()
        self.browser_executable = browser_executable or (
            str(self.runtime.browser_executable) if self.runtime.browser_executable else None
        )
        self.run = run
        self.process_runner = process_runner or CancellableProcessRunner()

    def render(
        self,
        graph: RenderGraphV2,
        output: Path,
        *,
        asset_base_url: str = "",
        control: ProcessControl | None = None,
        muted: bool = True,
    ) -> None:
        output.parent.mkdir(parents=True, exist_ok=True)
        props_path = output.with_name(f".{output.stem}.render-graph.json")
        props_path.write_text(
            json.dumps(
                {
                    "graph": graph.model_dump(mode="json"),
                    "assetBaseUrl": asset_base_url,
                    "executionMode": "final",
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        fps = graph.canvas.fps or graph.canvas.fps_num
        if fps is None:  # GraphCanvas validation guarantees this cannot happen.
            raise GraphRenderError("render graph canvas has no frame rate")
        frames = duration_to_frames(graph.duration_us, fps)
        command = [
            str(self.runtime.node_executable),
            str(self.runtime.remotion_cli),
            "render",
            str(self.runtime.remotion_entry),
            "RenderGraphV2",
            str(output),
            f"--props={props_path}",
            f"--frames=0-{frames - 1}",
            f"--public-dir={self.project_root}",
            "--codec=h264",
            "--concurrency=1",
            f"--timeout={self.timeout_ms}",
            "--log=error",
        ]
        if muted:
            command.append("--muted")
        if self.browser_executable:
            command.extend(
                [
                    f"--browser-executable={self.browser_executable}",
                    "--chrome-mode=chrome-for-testing",
                ]
            )
        try:
            if self.run is not None:
                self.run(command, self.runtime.root / "remotion")
            else:
                self._run(command, self.runtime.root / "remotion", control or NullProcessControl())
        finally:
            props_path.unlink(missing_ok=True)

    def _run(self, command: list[str], cwd: Path, control: ProcessControl) -> None:
        try:
            self.process_runner.run(command, cwd, control)
        except ProcessCancelled as error:
            raise RenderCancelled("RenderGraph 全片渲染已取消") from error
        except ProcessExecutionError as error:
            raise GraphRenderError("RenderGraph 全片渲染失败") from error
