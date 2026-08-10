import json
import os
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from workbench.domain.enums import NodeStatus
from workbench.domain.errors import ProjectPathViolation
from workbench.domain.models import ProjectManifest
from workbench.storage.file_hash import sha256_file
from workbench.storage.manifest_store import ManifestStore


def make_manifest(name: str = "项目一") -> ProjectManifest:
    now = datetime.now(UTC)
    return ProjectManifest(
        id=uuid4(),
        name=name,
        project_dir="项目一_20260803_1630",
        created_at=now,
        updated_at=now,
        current_step=1,
        status=NodeStatus.NOT_STARTED,
    )


def test_interrupted_replace_keeps_previous_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_dir = tmp_path / "项目一_20260803_1630"
    project_dir.mkdir()
    store = ManifestStore(tmp_path)
    original = make_manifest("原始名称")
    store.save(project_dir, original)
    real_replace = os.replace

    def fail_main_replace(source: str | Path, destination: str | Path) -> None:
        replacing_manifest = Path(destination).name == "project.json"
        using_temporary_file = Path(source).name.startswith(".project.json")
        if replacing_manifest and using_temporary_file:
            raise OSError("simulated process interruption")
        real_replace(source, destination)

    monkeypatch.setattr(os, "replace", fail_main_replace)

    with pytest.raises(OSError, match="simulated"):
        store.save(project_dir, make_manifest("不应生效"))

    assert store.load(project_dir).name == "原始名称"


def test_corrupt_primary_recovers_from_backup(tmp_path: Path) -> None:
    project_dir = tmp_path / "项目一_20260803_1630"
    project_dir.mkdir()
    store = ManifestStore(tmp_path)
    store.save(project_dir, make_manifest("备份版本"))
    store.save(project_dir, make_manifest("当前版本"))
    (project_dir / "project.json").write_text("{broken", encoding="utf-8")

    recovered = store.recover(project_dir)

    assert recovered.name == "备份版本"
    assert json.loads((project_dir / "project.json").read_text("utf-8"))["name"] == "备份版本"


def test_file_hash_is_stable_and_content_sensitive(tmp_path: Path) -> None:
    source = tmp_path / "中文资料.txt"
    source.write_bytes("同一内容".encode())

    first = sha256_file(source)

    assert first == sha256_file(source)
    source.write_bytes("不同内容".encode())
    assert first != sha256_file(source)


def test_store_rejects_project_outside_workspace(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()

    with pytest.raises(ProjectPathViolation):
        ManifestStore(workspace).save(outside, make_manifest())
