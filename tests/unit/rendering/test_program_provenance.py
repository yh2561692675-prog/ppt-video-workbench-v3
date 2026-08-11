from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from workbench.quality.engine import QualityProcessResult, QualityService
from workbench.quality.models import QualityTarget
from workbench.rendering.export_pipeline import RenderGraphExportPipeline
from workbench.rendering.extensions import RenderExtensionProvenance
from workbench.rendering.hashing import sha256_json
from workbench.rendering.models import GraphCanvas, RenderGraphV2


class FakeGraphRunner:
    def render(self, graph, output, *, control, muted, execution_mode):
        output.write_bytes(b"video-only")


def _graph() -> RenderGraphV2:
    graph = RenderGraphV2(
        project_id=uuid4(),
        timeline_revision=1,
        duration_us=1_000_000,
        canvas=GraphCanvas(width=1920, height=1080, fps=30),
        graph_hash="0" * 64,
    )
    return graph.model_copy(
        update={
            "graph_hash": sha256_json(
                graph.model_dump(mode="json", exclude={"graph_hash", "created_at"})
            )
        }
    )


def test_render_package_binds_extension_provenance(tmp_path: Path) -> None:
    graph = _graph()
    provenance = RenderExtensionProvenance(
        base_graph_hash=graph.graph_hash,
        effective_graph_hash=graph.graph_hash,
    )

    def run(command: list[str], _: Path) -> None:
        Path(command[-1]).write_bytes(b"ffmpeg-output")

    result = RenderGraphExportPipeline(
        tmp_path,
        runner=FakeGraphRunner(),
        run=run,
    ).export(graph, tmp_path / "out", extension_provenance=provenance)
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["extension_provenance"] == "render-provenance.json"
    evidence = json.loads((tmp_path / "out" / "render-provenance.json").read_text())
    assert evidence["effective_graph_hash"] == graph.graph_hash


def test_quality_report_binds_render_provenance_without_schema_fork(tmp_path: Path) -> None:
    video = tmp_path / "final.mp4"
    video.write_bytes(b"not-a-real-video")

    def runner(command, cwd):
        if command[0] == "ffprobe":
            return QualityProcessResult(returncode=1)
        return QualityProcessResult(returncode=0)

    report = QualityService(runner=runner).analyze(
        project_id=uuid4(),
        render_job_id=uuid4(),
        target=QualityTarget(
            video_path=video,
            expected_width=1920,
            expected_height=1080,
            expected_duration_ms=1_000,
        ),
        render_provenance={
            "render-graph": "2.0",
            "effects-source": "3e5f310aee7157486944cc055a0f2d62a9418582",
        },
    )
    assert report.analyzer_versions["render-graph"] == "2.0"
    assert report.analyzer_versions["effects-source"].startswith("3e5f310")

    changed = QualityService(runner=runner).analyze(
        project_id=report.project_id,
        render_job_id=report.render_job_id,
        target=QualityTarget(
            video_path=video,
            expected_width=1920,
            expected_height=1080,
            expected_duration_ms=1_000,
        ),
        render_provenance={"render-graph": "2.0", "effects-source": "different"},
    )
    assert changed.input_fingerprint != report.input_fingerprint
