from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from workbench.environment.detector import EnvironmentDetector
from workbench.main import create_app


def test_environment_report_and_diagnostic_package_routes(tmp_path: Path) -> None:
    detector = EnvironmentDetector(
        tmp_path,
        component_probe=lambda name: ("3.12.0", f"/runtime/{name}"),
    )
    app = create_app(tmp_path, environment_detector=detector)

    with TestClient(app) as client:
        report = client.get("/api/environment")
        package = client.post("/api/environment/diagnostic-package")

    assert report.status_code == 200
    assert report.json()["data"]["checks"]
    assert package.status_code == 200
    assert package.json()["data"]["relative_path"].startswith("09_日志/诊断/")
    assert (tmp_path / package.json()["data"]["relative_path"]).is_file()
