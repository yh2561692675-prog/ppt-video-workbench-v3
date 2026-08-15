from __future__ import annotations

import hashlib
from pathlib import Path

from fastapi.testclient import TestClient
from workbench.main import create_app


def _descriptor(content: bytes) -> dict[str, object]:
    return {
        "schema_version": 1,
        "model_id": "demo-asr",
        "display_name": "Demo ASR",
        "kind": "asr",
        "engine": "fixture",
        "engine_version": "1.0",
        "revision": "r1",
        "source_ref": "local-fixture",
        "supported_languages": ["zh-CN"],
        "capabilities": ["transcribe"],
        "license_ref": "internal-test",
        "files": [
            {
                "schema_version": 1,
                "relative_path": "model.bin",
                "size_bytes": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
            }
        ],
        "supported_devices": ["cpu"],
        "runtime_contract_version": "1.0",
        "compatible_app_versions": ["0.1"],
        "remote_download_required": False,
        "redistribution_allowed": False,
    }


def test_local_model_center_install_probe_and_activate(tmp_path: Path) -> None:
    source = tmp_path / "fixtures" / "demo-asr"
    source.mkdir(parents=True)
    content = b"fixture-model"
    (source / "model.bin").write_bytes(content)

    with TestClient(create_app(tmp_path)) as client:
        initial = client.get("/api/ai/models")
        assert initial.status_code == 200
        assert initial.json()["data"] == []

        installed = client.post(
            "/api/ai/models/install",
            json={
                "descriptor": _descriptor(content),
                "source_relative_path": "fixtures/demo-asr",
            },
        )
        assert installed.status_code == 201, installed.text
        assert installed.json()["data"]["install"]["status"] == "ready"

        probed = client.post("/api/ai/models/demo-asr/probe", json={"device": "cpu"})
        assert probed.status_code == 200, probed.text
        assert probed.json()["data"]["status"] == "available"

        activated = client.post("/api/ai/models/demo-asr/activate?revision=r1")
        assert activated.status_code == 200, activated.text
        assert activated.json()["data"]["install"]["status"] == "active"


def test_model_install_rejects_workspace_escape(tmp_path: Path) -> None:
    content = b"fixture-model"
    outside = tmp_path.parent / "outside-model"
    outside.mkdir()
    (outside / "model.bin").write_bytes(content)

    with TestClient(create_app(tmp_path)) as client:
        response = client.post(
            "/api/ai/models/install",
            json={
                "descriptor": _descriptor(content),
                "source_relative_path": "../outside-model",
            },
        )

    assert response.status_code == 422
