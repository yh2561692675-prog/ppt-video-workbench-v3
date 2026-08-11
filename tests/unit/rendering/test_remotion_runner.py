from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from workbench.rendering.models import GraphCanvas, RenderGraphV2
from workbench.rendering.remotion_runner import RemotionGraphRunner
from workbench.runtime.layout import RendererRuntime


def test_remotion_graph_runner_renders_full_composition_once(tmp_path: Path) -> None:
    runtime_root = tmp_path / "runtime"
    paths = {}
    for relative, contents in {
        "node/node.exe": "node",
        "remotion/node_modules/@remotion/cli/remotion-cli.js": "cli",
        "remotion/src/index.ts": "entry",
    }.items():
        path = runtime_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents, encoding="utf-8")
        paths[relative] = path
    runtime = RendererRuntime(
        root=runtime_root,
        node_executable=paths["node/node.exe"],
        remotion_cli=paths["remotion/node_modules/@remotion/cli/remotion-cli.js"],
        remotion_entry=paths["remotion/src/index.ts"],
        ffmpeg_executable=None,
        ffprobe_executable=None,
        browser_executable=None,
    )
    calls: list[list[str]] = []
    props: list[dict[str, object]] = []

    def run(command: list[str], _: Path) -> None:
        calls.append(command)
        props_path = next(
            Path(argument.removeprefix("--props="))
            for argument in command
            if argument.startswith("--props=")
        )
        props.append(json.loads(props_path.read_text(encoding="utf-8")))

    runner = RemotionGraphRunner(
        tmp_path, runtime=runtime, run=run
    )
    graph = RenderGraphV2(
        project_id=uuid4(),
        timeline_revision=1,
        duration_us=2_000_000,
        canvas=GraphCanvas(width=1920, height=1080, fps=30),
        graph_hash="0" * 64,
    )
    output = tmp_path / "rendered.mp4"
    runner.render(graph, output, execution_mode="authoritative-preview")
    assert len(calls) == 1
    assert "RenderGraphV2" in calls[0]
    assert "--frames=0-59" in calls[0]
    assert props[0]["executionMode"] == "authoritative-preview"
    assert not list(tmp_path.glob(".*.render-graph.json"))
