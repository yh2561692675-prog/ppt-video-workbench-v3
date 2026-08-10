from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from workbench_peripheral_adapter.dto import ArtifactDto, JobStatusDto, SubmitJobResultDto


class FakeAdapter:
    enabled = True

    def __init__(self, payload: bytes) -> None:
        self.payload = payload
        self.job_id = uuid4()
        self.project_id = uuid4()
        self.artifact_id = uuid4()

    def submit_job(self, request):
        self.job_id = request.job_id
        self.project_id = request.project_id
        return SubmitJobResultDto(job_id=self.job_id, status="queued", created=True)

    def get_job_status(self, job_id):
        return JobStatusDto(
            schema_version="1.0",
            job_id=job_id,
            project_id=self.project_id,
            job_type="document.extract",
            status="succeeded",
            attempt_count=1,
            progress=100,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

    def list_artifacts(self, job_id):
        return (
            ArtifactDto(
                artifact_id=self.artifact_id,
                job_id=job_id,
                project_id=self.project_id,
                logical_name="business-result",
                kind="json",
                version=1,
                size_bytes=len(self.payload),
                sha256=hashlib.sha256(self.payload).hexdigest(),
                verified_at=datetime.now(UTC),
                is_current=True,
            ),
        )

    def stream_artifact(self, job_id, artifact_id):
        yield self.payload


def test_reconcile_pending_projection_is_applied_once(tmp_path: Path) -> None:
    from workbench.peripheral_s1.coordinator import JobSpec, S1Coordinator, input_fingerprint
    from workbench.peripheral_s1.inbox import ProjectionInbox
    from workbench.peripheral_s1.projector import ProjectorRegistry
    from workbench.storage.workspace_db import WorkspaceDatabase

    project_id = uuid4()
    adapter = FakeAdapter(b"")
    database = WorkspaceDatabase(tmp_path / "workspace.db")
    database.initialize()
    inbox = ProjectionInbox(database)
    registry = ProjectorRegistry()
    applied = []
    registry.register("document_extraction", lambda result, root: applied.append(result.payload))
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    (project_dir / "project.json").write_text('{"revision":1}', encoding="utf-8")
    coordinator = S1Coordinator(
        workspace_root=tmp_path,
        adapter=adapter,
        inbox=inbox,
        projector=registry,
        project_dir_resolver=lambda _project_id: project_dir,
        database=database,
    )
    spec = JobSpec(
        project_id=project_id,
        project_revision=1,
        module_id="P04",
        job_type="document.extract",
        affected_page_ids=(),
        inputs=(),
        parameters={},
        runtime_version="1.0.0",
        requested_by="test",
    )
    submitted = coordinator.submit(spec)
    persisted_spec = coordinator._specs[submitted.job_id]
    adapter.payload = json.dumps(
        {
            "schema_version": "1.0",
            "module_id": "P04",
            "job_type": "document.extract",
            "project_id": str(project_id),
            "project_revision": 1,
            "input_fingerprint": input_fingerprint(persisted_spec),
            "cache_key": "b" * 64,
            "result_type": "document_extraction",
            "payload": {"page_count": 2},
            "artifacts": [],
        }
    ).encode()

    restarted = S1Coordinator(
        workspace_root=tmp_path,
        adapter=adapter,
        inbox=inbox,
        projector=registry,
        project_dir_resolver=lambda _project_id: project_dir,
        database=database,
    )

    first = restarted.reconcile(submitted.job_id)
    second = restarted.reconcile(submitted.job_id)

    assert first.status == "applied"
    assert second.status == "already_applied"
    assert applied == [{"page_count": 2}]
    assert restarted.submit(spec).status == "succeeded"


def test_reconcile_quarantines_result_when_project_snapshot_changed(tmp_path: Path) -> None:
    from workbench.peripheral_s1.coordinator import JobSpec, S1Coordinator, input_fingerprint
    from workbench.peripheral_s1.inbox import ProjectionInbox
    from workbench.peripheral_s1.projector import ProjectorRegistry
    from workbench.storage.workspace_db import WorkspaceDatabase

    project_id = uuid4()
    adapter = FakeAdapter(b"")
    database = WorkspaceDatabase(tmp_path / "workspace.db")
    database.initialize()
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    manifest_path = project_dir / "project.json"
    manifest_path.write_text('{"revision":1}', encoding="utf-8")
    applied = []
    registry = ProjectorRegistry()
    registry.register("document_extraction", lambda result, root: applied.append(result.payload))
    coordinator = S1Coordinator(
        workspace_root=tmp_path,
        adapter=adapter,
        inbox=ProjectionInbox(database),
        projector=registry,
        project_dir_resolver=lambda _project_id: project_dir,
        database=database,
    )
    spec = JobSpec(
        project_id=project_id,
        project_revision=1,
        module_id="P04",
        job_type="document.extract",
        affected_page_ids=(),
        inputs=(),
        parameters={},
        runtime_version="1.0.0",
        requested_by="test",
    )
    submitted = coordinator.submit(spec)
    persisted_spec = coordinator._specs[submitted.job_id]
    adapter.payload = json.dumps(
        {
            "schema_version": "1.0",
            "module_id": "P04",
            "job_type": "document.extract",
            "project_id": str(project_id),
            "project_revision": 1,
            "input_fingerprint": input_fingerprint(persisted_spec),
            "cache_key": "b" * 64,
            "result_type": "document_extraction",
            "payload": {"page_count": 2},
            "artifacts": [],
        }
    ).encode()
    manifest_path.write_text('{"revision":2}', encoding="utf-8")

    outcome = coordinator.reconcile(submitted.job_id)

    assert outcome.status == "quarantined"
    assert outcome.reason is not None and outcome.reason.startswith("STALE_PROJECT_REVISION")
    assert applied == []
