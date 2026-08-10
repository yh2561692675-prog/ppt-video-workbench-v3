from __future__ import annotations

import hashlib
from pathlib import Path
from uuid import UUID

from fastapi.testclient import TestClient
from workbench.domain.enums import NodeStatus
from workbench.domain.models import NarrationRecord, PageRecord, stable_page_id
from workbench.main import create_app


def _project_with_page(client: TestClient, app: object) -> tuple[str, str, Path]:
    project = client.post("/api/projects", json={"name": "旁白版本测试"}).json()["data"]
    project_id = UUID(project["id"])
    page_id = stable_page_id(project_id, 1)
    service = app.state.project_service  # type: ignore[attr-defined]
    manifest = service.get(project_id)
    service.save(
        manifest.model_copy(
            update={
                "pages": [
                    PageRecord(
                        id=page_id,
                        order=1,
                        title="专业概览",
                        status=NodeStatus.COMPLETED,
                    )
                ]
            }
        )
    )
    return project["id"], str(page_id), Path(project["project_dir"])


def test_revisions_are_immutable_and_restore_creates_a_new_revision(tmp_path: Path) -> None:
    app = create_app(tmp_path)
    with TestClient(app) as client:
        project_id, page_id, project_dir = _project_with_page(client, app)
        first = client.post(
            f"/api/projects/{project_id}/narrations/{page_id}/revisions",
            json={"text": "第一版旁白。", "author": "规划师", "expected_revision_id": None},
        )
        assert first.status_code == 201
        first_revision = first.json()["data"]
        first_path = (
            tmp_path
            / project_dir
            / "04_旁白"
            / "历史版本"
            / page_id
            / f"{first_revision['id']}.json"
        )
        first_hash = hashlib.sha256(first_path.read_bytes()).hexdigest()

        second = client.post(
            f"/api/projects/{project_id}/narrations/{page_id}/revisions",
            json={
                "text": "第二版旁白，信息更清晰。",
                "author": "规划师",
                "expected_revision_id": first_revision["id"],
            },
        )
        assert second.status_code == 201
        second_revision = second.json()["data"]

        stale = client.post(
            f"/api/projects/{project_id}/narrations/{page_id}/revisions",
            json={
                "text": "过期窗口中的修改。",
                "author": "规划师",
                "expected_revision_id": first_revision["id"],
            },
        )
        assert stale.status_code == 409
        assert stale.json()["error"]["code"] == "narration_edit_conflict"

        restored = client.post(
            f"/api/projects/{project_id}/narrations/{page_id}/restore/{first_revision['id']}",
            json={"actor": "规划师", "expected_revision_id": second_revision["id"]},
        )
        assert restored.status_code == 200
        restored_revision = restored.json()["data"]
        assert restored_revision["id"] not in {first_revision["id"], second_revision["id"]}
        assert restored_revision["text"] == "第一版旁白。"
        assert restored_revision["restored_from_revision_id"] == first_revision["id"]
        assert hashlib.sha256(first_path.read_bytes()).hexdigest() == first_hash

        history = client.get(f"/api/projects/{project_id}/narrations/{page_id}/revisions").json()[
            "data"
        ]
        assert [revision["version"] for revision in history] == [1, 2, 3]

    reopened = create_app(tmp_path)
    with TestClient(reopened) as client:
        history_after_restart = client.get(
            f"/api/projects/{project_id}/narrations/{page_id}/revisions"
        ).json()["data"]
    assert [revision["text"] for revision in history_after_restart] == [
        "第一版旁白。",
        "第二版旁白，信息更清晰。",
        "第一版旁白。",
    ]


def test_editing_confirmed_text_invalidates_confirmation(tmp_path: Path) -> None:
    app = create_app(tmp_path)
    with TestClient(app) as client:
        project_id, page_id, _ = _project_with_page(client, app)
        first = client.post(
            f"/api/projects/{project_id}/narrations/{page_id}/revisions",
            json={"text": "已确认文本。", "author": "规划师", "expected_revision_id": None},
        ).json()["data"]
        service = app.state.project_service
        manifest = service.get(UUID(project_id))
        page = manifest.pages[0]
        page.narration = NarrationRecord(
            id=UUID(first["id"]),
            revision_id=UUID(first["id"]),
            text=first["text"],
            status=NodeStatus.COMPLETED,
            confirmed_revision_id=UUID(first["id"]),
        )
        service.save(manifest)

        edited = client.post(
            f"/api/projects/{project_id}/narrations/{page_id}/revisions",
            json={
                "text": "确认后又修改的文本。",
                "author": "规划师",
                "expected_revision_id": first["id"],
            },
        )

    assert edited.status_code == 201
    saved_manifest = app.state.project_service.get(UUID(project_id))
    narration = saved_manifest.pages[0].narration
    assert narration is not None
    assert narration.status == NodeStatus.NEEDS_CONFIRMATION
    assert narration.confirmed_revision_id is None
    assert any(
        event.action == "narration_confirmation_invalidated" for event in saved_manifest.audit_log
    )
