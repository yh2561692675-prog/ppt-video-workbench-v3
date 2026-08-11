from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from workbench_peripheral_adapter.dto import SubmitJobResultDto


class FakeAdapter:
    enabled = True

    def __init__(self) -> None:
        self.requests = []

    def submit_job(self, request):
        self.requests.append(request)
        return SubmitJobResultDto(job_id=request.job_id, status="queued", created=True)


def test_submit_is_idempotent_for_canonical_spec(tmp_path: Path) -> None:
    from workbench.peripheral_s1.coordinator import JobSpec, S1Coordinator, input_fingerprint

    adapter = FakeAdapter()
    coordinator = S1Coordinator(workspace_root=tmp_path, adapter=adapter)
    project_id = uuid4()
    spec = JobSpec(
        project_id=project_id,
        project_revision=3,
        module_id="P04",
        job_type="document.extract",
        affected_page_ids=(uuid4(),),
        inputs=(),
        parameters={"ocr": True, "language": "zh"},
        runtime_version="1.0.0",
        requested_by="test",
    )

    first = coordinator.submit(spec)
    second = coordinator.submit(spec)

    assert first.job_id == second.job_id
    assert second.created is False
    assert len(adapter.requests) == 1
    assert first.idempotency_key == second.idempotency_key
    assert len(first.idempotency_key) == 64
    assert adapter.requests[0].parameters["input_fingerprint"] == input_fingerprint(spec)


def test_submission_survives_coordinator_restart(tmp_path: Path) -> None:
    from workbench.peripheral_s1.coordinator import JobSpec, S1Coordinator
    from workbench.storage.workspace_db import WorkspaceDatabase

    database = WorkspaceDatabase(tmp_path / "workspace.db")
    database.initialize()
    spec = JobSpec(
        project_id=uuid4(),
        project_revision=1,
        module_id="P03",
        job_type="material.ingest",
        affected_page_ids=(),
        inputs=(),
        parameters={"files": []},
        runtime_version="1.0.0",
        requested_by="test",
    )
    first_adapter = FakeAdapter()
    first = S1Coordinator(workspace_root=tmp_path, adapter=first_adapter, database=database)
    submitted = first.submit(spec)

    second_adapter = FakeAdapter()
    second = S1Coordinator(workspace_root=tmp_path, adapter=second_adapter, database=database)
    restored = second.submit(spec)

    assert restored.job_id == submitted.job_id
    assert restored.created is False
    assert second_adapter.requests == []


def test_project_snapshot_participates_in_submission_identity(tmp_path: Path) -> None:
    from workbench.peripheral_s1.coordinator import JobSpec, S1Coordinator

    project_id = uuid4()
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    manifest_path = project_dir / "project.json"
    manifest_path.write_text('{"revision":1}', encoding="utf-8")
    adapter = FakeAdapter()
    coordinator = S1Coordinator(
        workspace_root=tmp_path,
        adapter=adapter,
        project_dir_resolver=lambda _project_id: project_dir,
    )
    spec = JobSpec(
        project_id=project_id,
        project_revision=1,
        module_id="P03",
        job_type="material.ingest",
        affected_page_ids=(),
        inputs=(),
        parameters={"files": []},
        runtime_version="1.0.0",
        requested_by="test",
    )

    first = coordinator.submit(spec)
    manifest_path.write_text('{"revision":2}', encoding="utf-8")
    second = coordinator.submit(spec)

    assert first.job_id != second.job_id
    assert len(adapter.requests) == 2


def test_artifact_destination_finds_nested_descriptor() -> None:
    from workbench.peripheral_s1.coordinator import _artifact_destination

    payload = {
        "video": {
            "logical_name": "final-video",
            "relative_path": "08_输出/最终视频.mp4",
            "sha256": "a" * 64,
        }
    }

    assert (
        _artifact_destination(payload, logical_name="final-video", sha256="a" * 64)
        == "08_输出/最终视频.mp4"
    )


def test_artifact_destination_preserves_material_safe_name_rule() -> None:
    from workbench.peripheral_s1.coordinator import _artifact_destination

    payload = {"sources": [{"safe_name": "slides.pdf", "sha256": "b" * 64}]}

    assert _artifact_destination(payload, logical_name="source-slides", sha256="b" * 64) == str(
        Path("01_源文件") / "slides.pdf"
    )
