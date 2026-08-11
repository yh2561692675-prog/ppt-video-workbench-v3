from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from PIL import Image
from workbench.assets.models import AssetDeriveRequest, AssetImportRequest, AssetKind
from workbench.assets.service import AssetRegistryService
from workbench.domain.enums import JobStatus, JobType
from workbench.jobs.repository import JobRepository
from workbench.storage.workspace_db import WorkspaceDatabase


def test_derivative_job_materializes_and_publishes_independent_asset(tmp_path: Path) -> None:
    database = WorkspaceDatabase(tmp_path / "workspace.db")
    database.initialize()
    jobs = JobRepository(database)
    project_id = uuid4()
    project_root = tmp_path / "project"
    project_root.mkdir()
    Image.new("RGBA", (100, 80), (255, 0, 0, 128)).save(project_root / "image.png")
    service = AssetRegistryService(
        tmp_path,
        project_dir_resolver=lambda _: "project",
        jobs=jobs,
    )
    parent = service.import_asset(
        project_id,
        AssetImportRequest(relative_path="image.png", kind=AssetKind.IMAGE),
    )
    request = AssetDeriveRequest(
        parent_asset_id=parent.asset_id,
        operation="thumbnail",
        parameters={"width": 50, "height": 50},
    )

    submitted = service.submit_derivative(project_id, request)
    claimed = jobs.claim_next(JobType.DERIVE_ASSET)
    assert claimed is not None
    service.handle_derivative_job(claimed)

    completed = jobs.get(submitted.id)
    assert completed.status is JobStatus.SUCCEEDED
    derived = next(
        item for item in service.list_assets(project_id) if item.derived_from == parent.asset_id
    )
    assert derived.derived_from == parent.asset_id
    assert derived.content_hash != parent.content_hash
    assert (tmp_path / derived.relative_object_path).is_file()
    assert service.submit_derivative(project_id, request).id == submitted.id
