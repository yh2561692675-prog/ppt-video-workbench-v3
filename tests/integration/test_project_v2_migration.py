from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from workbench.api.migrations import create_migrations_router
from workbench.migrations.journal import MigrationStage
from workbench.migrations.project_v2 import ProjectMigrationError, ProjectV2Migration
from workbench.rendering.legacy_adapter import LegacyFallbackForbidden
from workbench.rendering.project_reader import ProjectRenderSourceReader
from workbench.services.project_service import ProjectService


def _valid_legacy_project(root: Path) -> dict[str, object]:
    fixture = json.loads(
        Path("tests/fixtures/legacy-project-v1.json").read_text(encoding="utf-8")
    )
    payload = fixture["manifest"]
    pages = payload["pages"]
    for index, page in enumerate(pages, start=1):
        page["order"] = index
        page["preview_path"] = f"02_pages/page-{index:04d}.png"
        page["audio"] = {
            "relative_path": f"05_audio/page-{index:04d}.wav",
            "duration_ms": 2000,
        }
        page["timeline"] = {
            "start_ms": (index - 1) * 2000,
            "end_ms": index * 2000,
        }
    root.mkdir()
    files = dict(fixture["files"])
    for index in range(2, 4):
        files[f"02_pages/page-{index:04d}.png"] = f"image-{index}"
        files[f"05_audio/page-{index:04d}.wav"] = f"audio-{index}"
    for relative, contents in files.items():
        path = root.joinpath(*relative.split("/"))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(contents.encode("utf-8"))
    (root / "project.json").write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8"
    )
    return payload


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _protected_hashes(root: Path) -> dict[str, str]:
    return {
        relative: _hash(root.joinpath(*relative.split("/")))
        for relative in [
            "project.json",
            "02_pages/page-0001.png",
            "05_audio/page-0001.wav",
            "06_subtitles/subtitles.srt",
            "08_output/legacy-final.mp4",
        ]
    }


def test_project_v2_migration_is_reentrant_preserves_legacy_and_rolls_back(
    tmp_path: Path,
) -> None:
    root = tmp_path / "legacy"
    payload = _valid_legacy_project(root)
    before = _protected_hashes(root)
    migration = ProjectV2Migration(root)

    first_plan = migration.preview(payload)
    second_plan = migration.preview(payload)
    assert first_plan.plan_hash == second_plan.plan_hash
    assert first_plan.required_bytes > 0
    assert first_plan.migratable

    first = migration.execute(first_plan, payload)
    repeated = migration.execute(first_plan, payload)
    assert first == repeated
    assert _protected_hashes(root) == before
    bundle = root / first.bundle_relative_path
    assert (bundle / "render-graph.json").is_file()
    source = ProjectRenderSourceReader(root).open(payload)
    assert source.mode == "v2"
    assert source.graph is not None and source.graph.graph_hash == first.graph_hash

    feature_disabled = ProjectRenderSourceReader(root).open(
        payload, migration_enabled=False
    )
    assert feature_disabled.mode == "legacy"
    assert feature_disabled.audit.action == "legacy_project_fallback"

    migration.rollback(first_plan.plan_hash)
    pointer = json.loads((root / first.pointer_relative_path).read_text(encoding="utf-8"))
    assert pointer["active"] is False
    assert bundle.is_dir()
    assert _protected_hashes(root) == before
    assert ProjectRenderSourceReader(root).open(payload).mode == "legacy"


def test_interrupted_migration_cleans_staging_and_resumes(tmp_path: Path) -> None:
    root = tmp_path / "legacy"
    payload = _valid_legacy_project(root)
    before = _protected_hashes(root)
    raised = False

    def fault(stage: MigrationStage) -> None:
        nonlocal raised
        if stage is MigrationStage.WRITE and not raised:
            raised = True
            raise RuntimeError("simulated interruption")

    migration = ProjectV2Migration(root, fault_hook=fault)
    plan = migration.preview(payload)
    with pytest.raises(RuntimeError, match="simulated interruption"):
        migration.execute(plan, payload)
    assert not (root / "07_视频工程" / f".migration-{plan.plan_hash}").exists()
    assert _protected_hashes(root) == before

    result = ProjectV2Migration(root).execute(plan, payload)
    assert result.committed
    assert _protected_hashes(root) == before


def test_blocking_legacy_damage_is_reported_before_writes(tmp_path: Path) -> None:
    fixture = json.loads(
        Path("tests/fixtures/legacy-project-v1.json").read_text(encoding="utf-8")
    )
    root = tmp_path / "damaged"
    root.mkdir()
    migration = ProjectV2Migration(root)
    plan = migration.preview(fixture["manifest"])

    assert not plan.migratable
    with pytest.raises(ProjectMigrationError, match="blocking legacy issues"):
        migration.execute(plan, fixture["manifest"])
    assert not (root / "07_视频工程").exists()


def test_disk_shortage_blocks_before_migration_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "legacy"
    payload = _valid_legacy_project(root)
    migration = ProjectV2Migration(root)
    plan = migration.preview(payload)
    before = _protected_hashes(root)
    monkeypatch.setattr(
        "workbench.migrations.project_v2.shutil.disk_usage",
        lambda _: SimpleNamespace(free=0),
    )

    with pytest.raises(ProjectMigrationError, match="insufficient disk space"):
        migration.execute(plan, payload)
    assert _protected_hashes(root) == before
    assert not (root / "07_视频工程").exists()


def test_invalid_v2_bundle_falls_back_only_for_nonexclusive_project(tmp_path: Path) -> None:
    root = tmp_path / "legacy"
    payload = _valid_legacy_project(root)
    migration = ProjectV2Migration(root)
    plan = migration.preview(payload)
    result = migration.execute(plan, payload)
    (root / result.bundle_relative_path / "render-graph.json").write_text(
        "{}", encoding="utf-8"
    )

    fallback = ProjectRenderSourceReader(root).open(payload, renderer_generation="v1")
    assert fallback.mode == "legacy"
    assert "invalid V2 migration" in fallback.audit.reason
    with pytest.raises(LegacyFallbackForbidden, match="cannot use legacy fallback"):
        ProjectRenderSourceReader(root).open(payload, renderer_generation="v2")


def test_migration_and_dual_read_api_support_raw_legacy_manifest(tmp_path: Path) -> None:
    projects = ProjectService(tmp_path / "workspace")
    project = projects.create("legacy-api")
    root = projects.workspace_root / project.project_dir
    fixture = json.loads(
        Path("tests/fixtures/legacy-project-v1.json").read_text(encoding="utf-8")
    )
    fixture["manifest"]["id"] = str(project.id)
    (root / "project.json").write_text(
        json.dumps(fixture["manifest"], ensure_ascii=False), encoding="utf-8"
    )
    for relative, contents in fixture["files"].items():
        path = root.joinpath(*relative.split("/"))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(contents.encode("utf-8"))
    app = FastAPI()
    app.include_router(create_migrations_router(projects))

    with TestClient(app) as client:
        source = client.get(f"/api/projects/{project.id}/render-source")
        assert source.status_code == 200
        assert source.json()["data"]["mode"] == "legacy"

        exclusive = client.get(
            f"/api/projects/{project.id}/render-source?renderer_generation=v2"
        )
        assert exclusive.status_code == 409

        preview = client.post(f"/api/projects/{project.id}/migrations/v2/preview")
        assert preview.status_code == 200
        assert preview.json()["data"]["project_id"] == str(project.id)
        assert any(
            issue["severity"] == "blocking"
            for issue in preview.json()["data"]["issues"]
        )
    projects.close()
