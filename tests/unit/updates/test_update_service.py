from __future__ import annotations

import json
from pathlib import Path

import pytest
from workbench.updates.service import UpdateError, UpdateService, hash_update_package


def _package(workspace: Path, version: str, *, healthy: bool = True) -> Path:
    package = workspace / "updates" / version
    package.mkdir(parents=True)
    (package / "runtime-manifest.json").write_text(
        json.dumps({"version": version}), encoding="utf-8"
    )
    (package / "healthy.txt").write_text("ok", encoding="utf-8") if healthy else None
    return package


def _publish_manifest(workspace: Path, package: Path, *, channel: str = "stable") -> None:
    manifest = {
        "version": package.name,
        "channel": channel,
        "notes": "安全更新",
        "size": sum(path.stat().st_size for path in package.rglob("*")),
        "sha256": hash_update_package(package),
        "package_relative_path": package.relative_to(workspace).as_posix(),
    }
    releases = workspace / "releases"
    releases.mkdir(parents=True, exist_ok=True)
    (releases / "stable-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def _service(workspace: Path, *, healthy: bool = True, disk_free: int = 10**12) -> UpdateService:
    current = workspace / "releases" / "current"
    current.mkdir(parents=True, exist_ok=True)
    (current / "old-version.txt").write_text("1.0.0", encoding="utf-8")
    return UpdateService(
        workspace,
        current_version="1.0.0",
        health_check=(lambda path: healthy and (path / "healthy.txt").exists()),
        disk_free=lambda _: disk_free,
    )


def test_stable_update_is_staged_and_applied_without_touching_projects(tmp_path: Path) -> None:
    projects = tmp_path / "projects" / "demo"
    projects.mkdir(parents=True)
    project_marker = projects / "project.json"
    project_marker.write_text('{"name":"demo"}', encoding="utf-8")
    settings = tmp_path / "settings"
    settings.mkdir()
    (settings / "profiles.json").write_text('{"profile":"local"}', encoding="utf-8")

    package = _package(tmp_path, "1.1.0")
    _publish_manifest(tmp_path, package)
    service = _service(tmp_path)

    candidate = service.check_update()
    assert candidate is not None
    assert candidate.channel == "stable"
    assert service.stage_update(package).staged_version == "1.1.0"

    state = service.apply_update()

    assert state.status == "applied"
    assert state.current_version == "1.1.0"
    assert (tmp_path / "releases" / "previous" / "old-version.txt").read_text() == "1.0.0"
    assert project_marker.read_text() == '{"name":"demo"}'
    assert (tmp_path / "update-backups").exists()


def test_hash_failure_is_rejected_before_staging(tmp_path: Path) -> None:
    package = _package(tmp_path, "1.1.0")
    _publish_manifest(tmp_path, package)
    manifest_path = tmp_path / "releases" / "stable-manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["sha256"] = "0" * 64
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    service = _service(tmp_path)

    with pytest.raises(UpdateError, match="哈希") as error:
        service.stage_update(package)

    assert error.value.code == "package_hash_mismatch"
    assert not (tmp_path / "releases" / "staged").exists()


def test_health_failure_restores_old_version_settings_and_projects(tmp_path: Path) -> None:
    package = _package(tmp_path, "1.1.0", healthy=False)
    _publish_manifest(tmp_path, package)
    settings = tmp_path / "settings"
    settings.mkdir()
    setting = settings / "profiles.json"
    setting.write_text("old", encoding="utf-8")
    service = _service(tmp_path, healthy=False)

    service.stage_update(package)
    with pytest.raises(UpdateError, match="健康检查") as error:
        service.apply_update()

    assert error.value.code == "health_check_failed"
    assert service.state().status == "rolled_back"
    assert (tmp_path / "releases" / "current" / "old-version.txt").read_text() == "1.0.0"
    assert not (tmp_path / "releases" / "current" / "runtime-manifest.json").exists()
    assert setting.read_text() == "old"


def test_disk_space_and_non_stable_channel_are_blocked(tmp_path: Path) -> None:
    package = _package(tmp_path, "1.1.0")
    _publish_manifest(tmp_path, package, channel="beta")
    service = _service(tmp_path, disk_free=0)

    with pytest.raises(UpdateError) as error:
        service.check_update()
    assert error.value.code == "stable_channel_required"

    manifest_path = tmp_path / "releases" / "stable-manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["channel"] = "stable"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    service = _service(tmp_path, disk_free=0)
    service.check_update()
    with pytest.raises(UpdateError) as error:
        service.stage_update(package)
    assert error.value.code == "disk_space_low"


def test_manual_rollback_swaps_current_and_previous(tmp_path: Path) -> None:
    package = _package(tmp_path, "1.1.0")
    _publish_manifest(tmp_path, package)
    service = _service(tmp_path)
    service.stage_update(package)
    service.apply_update()

    state = service.rollback_update()

    assert state.status == "rolled_back"
    assert state.current_version == "1.0.0"
    assert (tmp_path / "releases" / "current" / "old-version.txt").exists()
