from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from workbench.assets.models import (
    AssetDeriveRequest,
    AssetImportRequest,
    AssetKind,
    LicenseRecord,
    LicenseStatus,
)
from workbench.assets.service import AssetRegistryError, AssetRegistryService


def test_import_is_content_addressed_and_deduplicated(tmp_path: Path) -> None:
    project_id = uuid4()
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "logo.png").write_bytes(b"logo-bytes")
    service = AssetRegistryService(tmp_path, project_dir_resolver=lambda _: "project")

    request = AssetImportRequest(relative_path="logo.png", kind=AssetKind.LOGO)
    first = service.import_asset(project_id, request)
    second = service.import_asset(project_id, request)

    assert first.asset_id == second.asset_id
    assert first.content_hash
    assert (tmp_path / first.relative_object_path).is_file()
    assert len(service.list_assets(project_id)) == 1


def test_import_rejects_path_escape(tmp_path: Path) -> None:
    service = AssetRegistryService(tmp_path, project_dir_resolver=lambda _: "project")
    with pytest.raises(AssetRegistryError, match="inside project"):
        service.import_asset(
            uuid4(), AssetImportRequest(relative_path="../secret.bin", kind=AssetKind.DOCUMENT)
        )


def test_license_revision_and_derived_reference_are_persisted(tmp_path: Path) -> None:
    project_id = uuid4()
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "clip.mp4").write_bytes(b"clip-bytes")
    service = AssetRegistryService(tmp_path, project_dir_resolver=lambda _: "project")
    source = service.import_asset(
        project_id,
        AssetImportRequest(relative_path="clip.mp4", kind=AssetKind.VIDEO),
    )
    confirmed = service.update_license(
        project_id,
        source.asset_id,
        LicenseRecord(status=LicenseStatus.CONFIRMED, owner="owner"),
    )
    derived = service.derive(
        project_id,
        AssetDeriveRequest(
            parent_asset_id=source.asset_id,
            operation="proxy",
            parameters={"width": 640},
        ),
    )

    assert confirmed.revision == 2
    assert derived.derived_from == source.asset_id
    assert derived.operation is not None and derived.operation.startswith("proxy:")
