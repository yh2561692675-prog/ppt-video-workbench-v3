import zipfile
from collections.abc import Callable
from pathlib import Path

from fastapi.testclient import TestClient
from workbench.diagnostics.center import CHECK_IDS, DiagnosticCenter
from workbench.diagnostics.models import (
    DiagnosticCategory,
    DiagnosticCheck,
    DiagnosticStatus,
)
from workbench.main import create_app


def _green(check_id: str) -> DiagnosticCheck:
    return DiagnosticCheck(
        check_id=check_id,
        label=check_id,
        status=DiagnosticStatus.GREEN,
        category=DiagnosticCategory.ENVIRONMENT,
        code=f"{check_id.upper()}_OK",
        summary="检查通过",
        impact="无影响",
        remediation="无需处理",
        evidence={},
    )


def _center(tmp_path: Path) -> DiagnosticCenter:
    probes: dict[str, Callable[[], DiagnosticCheck]] = {
        check_id: (lambda selected=check_id: _green(selected)) for check_id in CHECK_IDS
    }
    return DiagnosticCenter(tmp_path, probes=probes)


def test_run_latest_and_package_routes_share_the_same_report(tmp_path: Path) -> None:
    app = create_app(
        tmp_path,
        diagnostic_center_factory=lambda _: _center(tmp_path),
    )

    with TestClient(app) as client:
        assert client.get("/api/diagnostics/latest").status_code == 404
        run = client.post("/api/diagnostics/run")
        latest = client.get("/api/diagnostics/latest")
        package = client.post("/api/diagnostics/package")

    assert run.status_code == 200
    assert run.json()["data"]["summary"] == {"green": 13, "yellow": 0, "red": 0}
    assert latest.json()["data"]["report_id"] == run.json()["data"]["report_id"]
    assert package.json()["data"]["report_id"] == run.json()["data"]["report_id"]
    archive_path = tmp_path / package.json()["data"]["relative_path"]
    with zipfile.ZipFile(archive_path) as archive:
        assert "manifest.json" in archive.namelist()


def test_diagnostic_factory_failure_does_not_block_application_health(
    tmp_path: Path,
) -> None:
    def raising_factory(_: Path) -> DiagnosticCenter:
        raise RuntimeError("private bootstrap detail")

    app = create_app(tmp_path, diagnostic_center_factory=raising_factory)

    with TestClient(app) as client:
        health = client.get("/api/health")
        diagnostics = client.post("/api/diagnostics/run")
        projects = client.get("/api/projects")

    assert health.status_code == 200
    assert projects.status_code == 200
    assert diagnostics.status_code == 200
    payload = diagnostics.json()["data"]
    assert payload["overall_status"] == "red"
    assert len(payload["checks"]) == 13
    assert all(check["code"] == "DIAGNOSTIC_CENTER_UNAVAILABLE" for check in payload["checks"])
    assert "private bootstrap detail" not in str(payload)


def test_diagnostic_target_is_isolated_from_the_project_workspace(
    tmp_path: Path,
) -> None:
    project_workspace = tmp_path / "acceptance-project-workspace"
    diagnostic_target = tmp_path / "real-workspace"
    diagnostic_target.mkdir()
    selected_roots: list[Path] = []

    def center_factory(root: Path) -> DiagnosticCenter:
        selected_roots.append(root)
        return _center(root)

    app = create_app(
        project_workspace,
        diagnostic_root=diagnostic_target,
        diagnostic_center_factory=center_factory,
    )

    with TestClient(app) as client:
        assert client.post("/api/diagnostics/run").status_code == 200
        package = client.post("/api/diagnostics/package")

    assert selected_roots == [diagnostic_target]
    assert (project_workspace / "workspace.db").is_file()
    assert not (diagnostic_target / "workspace.db").exists()
    assert (diagnostic_target / package.json()["data"]["relative_path"]).is_file()
    assert not (project_workspace / "diagnostics").exists()


def test_diagnostic_target_can_be_selected_by_the_launcher_environment(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project_workspace = tmp_path / "acceptance-project-workspace"
    diagnostic_target = tmp_path / "real-workspace"
    diagnostic_target.mkdir()
    selected_roots: list[Path] = []
    monkeypatch.setenv("WORKBENCH_DIAGNOSTIC_ROOT", str(diagnostic_target))

    app = create_app(
        project_workspace,
        diagnostic_center_factory=lambda root: selected_roots.append(root) or _center(root),
    )

    with TestClient(app) as client:
        package = client.post("/api/diagnostics/run")

    assert package.status_code == 200
    assert selected_roots == [diagnostic_target]
    assert (project_workspace / "workspace.db").is_file()
    assert not (diagnostic_target / "workspace.db").exists()
