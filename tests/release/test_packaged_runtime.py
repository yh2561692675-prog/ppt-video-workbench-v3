from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from workbench import desktop
from workbench.main import create_app


def test_packaged_web_root_serves_single_page_app_without_shadowing_api(
    tmp_path: Path,
    monkeypatch,
) -> None:
    web_root = tmp_path / "web"
    web_root.mkdir()
    (web_root / "index.html").write_text("<h1>Packaged workbench</h1>", encoding="utf-8")
    monkeypatch.setenv("WORKBENCH_WEB_ROOT", str(web_root))

    with TestClient(create_app(tmp_path / "workspace")) as client:
        index = client.get("/")
        health = client.get("/api/health")
        refresh = client.get("/projects/demo")

    assert index.status_code == 200
    assert index.text == "<h1>Packaged workbench</h1>"
    assert health.status_code == 200
    assert health.json() == {"status": "ok"}
    assert refresh.status_code == 200
    assert refresh.text == "<h1>Packaged workbench</h1>"


def test_desktop_cli_starts_loopback_uvicorn_server(monkeypatch) -> None:
    observed: dict[str, object] = {}

    def record_run(app: object, *, host: str, port: int) -> None:
        observed["app"] = app
        observed["host"] = host
        observed["port"] = port

    monkeypatch.setattr(desktop.uvicorn, "run", record_run)

    desktop.main(["serve", "--host", "127.0.0.1", "--port", "18765"])

    assert callable(observed["app"])
    assert observed["host"] == "127.0.0.1"
    assert observed["port"] == 18765
