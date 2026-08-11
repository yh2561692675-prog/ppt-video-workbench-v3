from pathlib import Path

from fastapi.testclient import TestClient
from workbench.main import create_app
from workbench.media.presenter_probe import PresenterMediaError, PresenterMediaInfo


def _create_project(client: TestClient) -> dict[str, object]:
    response = client.post("/api/projects", json={"name": "真人讲解项目"})
    assert response.status_code == 201
    return response.json()["data"]


def test_presenter_upload_is_atomic_and_switches_mode(tmp_path: Path) -> None:
    def probe(path: Path) -> PresenterMediaInfo:
        assert path.name.endswith(".tmp")
        return PresenterMediaInfo(
            path=str(path),
            sha256="a" * 64,
            duration_ms=12_000,
            container="mov,mp4",
            video_codec="h264",
            audio_codec="aac",
            width=1920,
            height=1080,
            fps=30,
            sample_rate=48_000,
            channels=2,
        )

    with TestClient(create_app(tmp_path, presenter_probe=probe)) as client:
        project = _create_project(client)
        response = client.post(
            f"/api/projects/{project['id']}/presenter-source",
            files={"file": ("真人讲解.mp4", b"presenter", "video/mp4")},
        )

        assert response.status_code == 201
        saved = response.json()["data"]
        assert saved["presentation_mode"] == "human_presenter"
        assert saved["presenter_source"]["sha256"] == "a" * 64
        source = tmp_path / str(saved["project_dir"]) / saved["presenter_source"]["relative_path"]
        assert source.read_bytes() == b"presenter"
        assert not list(source.parent.glob("*.tmp"))


def test_failed_probe_preserves_manifest(tmp_path: Path) -> None:
    def reject(_: Path) -> PresenterMediaInfo:
        raise PresenterMediaError("PRESENTER_DECODE_FAILED", "broken")

    app = create_app(tmp_path, presenter_probe=reject)
    with TestClient(app) as client:
        project = _create_project(client)
        manifest = tmp_path / str(project["project_dir"]) / "project.json"
        before = manifest.read_bytes()
        response = client.post(
            f"/api/projects/{project['id']}/presenter-source",
            files={"file": ("broken.mp4", b"broken", "video/mp4")},
        )

        assert response.status_code == 422
        assert response.json()["error"]["code"] == "PRESENTER_DECODE_FAILED"
        assert manifest.read_bytes() == before
        assert not list(manifest.parent.rglob("*.tmp"))
