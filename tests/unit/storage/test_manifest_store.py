import json
import os
from concurrent.futures import ThreadPoolExecutor
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


def test_concurrent_saves_are_serialized_per_project(tmp_path: Path) -> None:
    project_dir = tmp_path / "项目一_20260803_1630"
    project_dir.mkdir()
    store = ManifestStore(tmp_path)
    names = [f"并发保存 {index}" for index in range(12)]

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(store.save, project_dir, make_manifest(name)) for name in names]
        for future in futures:
            future.result()

    assert store.load(project_dir).name in names
    assert not list(project_dir.glob(".project.json.*.tmp"))


def test_save_retries_a_transient_windows_sharing_violation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_dir = tmp_path / "项目一_20260803_1630"
    project_dir.mkdir()
    store = ManifestStore(tmp_path)
    store.save(project_dir, make_manifest("原始名称"))
    real_replace = os.replace
    attempts = 0

    def fail_then_replace(source: str | Path, destination: str | Path) -> None:
        nonlocal attempts
        is_main_replace = Path(destination).name == "project.json"
        if is_main_replace and attempts < 2:
            attempts += 1
            raise PermissionError(13, "sharing violation", None, 32)
        real_replace(source, destination)

    monkeypatch.setattr(os, "replace", fail_then_replace)
    monkeypatch.setattr("workbench.storage.manifest_store.sleep", lambda _: None)

    store.save(project_dir, make_manifest("重试成功"))

    assert attempts == 2
    assert store.load(project_dir).name == "重试成功"


def test_non_windows_permission_error_without_winerror_is_not_retried(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.json"
    destination = tmp_path / "destination.json"
    source.write_text("{}", encoding="utf-8")
    attempts = 0

    def fail_replace(_: str | Path, __: str | Path) -> None:
        nonlocal attempts
        attempts += 1
        raise PermissionError(13, "permission denied")

    monkeypatch.setattr(os, "replace", fail_replace)
    monkeypatch.setattr("workbench.storage.manifest_store.os.name", "posix")

    with pytest.raises(PermissionError, match="permission denied"):
        ManifestStore._replace_with_retry(source, destination)

    assert attempts == 1


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
