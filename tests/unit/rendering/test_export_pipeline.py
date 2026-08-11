from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from workbench.rendering.export_pipeline import GraphExportError, RenderGraphExportPipeline
from workbench.rendering.hashing import sha256_json
from workbench.rendering.models import GraphCanvas, RenderGraphV2


class FakeGraphRunner:
    def render(self, graph, output, *, control, muted):
        output.write_bytes(b"video-only")


def test_export_pipeline_runs_remotion_audio_and_final_mux_in_order(tmp_path: Path) -> None:
    commands: list[list[str]] = []

    def run(command: list[str], _: Path) -> None:
        commands.append(command)
        Path(command[-1]).write_bytes(b"ffmpeg-output")

    graph = RenderGraphV2(
        project_id=uuid4(),
        timeline_revision=3,
        duration_us=1_000_000,
        canvas=GraphCanvas(width=1920, height=1080, fps=30),
        graph_hash="0" * 64,
    )
    graph = graph.model_copy(
        update={
            "graph_hash": sha256_json(
                graph.model_dump(mode="json", exclude={"graph_hash", "created_at"})
            )
        }
    )
    result = RenderGraphExportPipeline(
        tmp_path,
        runner=FakeGraphRunner(),
        run=run,
    ).export(graph, tmp_path / "out")
    assert result.video_path.is_file()
    assert result.audio_path.is_file()
    assert len(commands) == 2
    assert "-filter_complex" in commands[0]
    assert "-map" in commands[1]
    assert json_text(result.manifest_path).find(graph.graph_hash) >= 0


def test_export_pipeline_rejects_missing_ffmpeg_artifact(tmp_path: Path) -> None:
    def run(command: list[str], _: Path) -> None:
        if command[-1].endswith("最终视频.mp4"):
            Path(command[-1]).write_bytes(b"final")

    graph = RenderGraphV2(
        project_id=uuid4(),
        timeline_revision=1,
        duration_us=1_000_000,
        canvas=GraphCanvas(width=1920, height=1080, fps=30),
        graph_hash="0" * 64,
    )
    graph = graph.model_copy(
        update={
            "graph_hash": sha256_json(
                graph.model_dump(mode="json", exclude={"graph_hash", "created_at"})
            )
        }
    )
    with pytest.raises(GraphExportError, match="master audio"):
        RenderGraphExportPipeline(tmp_path, runner=FakeGraphRunner(), run=run).export(
            graph, tmp_path / "out"
        )


def test_export_pipeline_uses_process_runner_without_test_callback(tmp_path: Path) -> None:
    calls: list[list[str]] = []

    class FakeProcessRunner:
        def run(self, command, cwd, control):
            calls.append(command)

    pipeline = RenderGraphExportPipeline(tmp_path, process_runner=FakeProcessRunner())
    pipeline._run_ffmpeg(["ffmpeg", "-version"], tmp_path, object())
    assert calls == [["ffmpeg", "-version"]]


def json_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")
