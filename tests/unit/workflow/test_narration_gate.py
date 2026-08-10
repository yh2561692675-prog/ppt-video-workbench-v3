from __future__ import annotations

from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from workbench.domain.enums import NodeStatus
from workbench.domain.matching import PageMatch
from workbench.domain.models import PageRecord, stable_page_id
from workbench.main import create_app
from workbench.narration.repository import NarrationRepository
from workbench.workflow.gates import ConfirmationError, NarrationGateService


def _ready_project(tmp_path: Path) -> tuple[object, object, list[UUID], list[UUID]]:
    app = create_app(tmp_path)
    service = app.state.project_service
    project = service.create("确认门禁")
    page_ids = [stable_page_id(project.id, order) for order in (1, 2)]
    service.save(
        project.model_copy(
            update={
                "pages": [
                    PageRecord(
                        id=page_id,
                        order=order,
                        title=f"第{order}页",
                        status=NodeStatus.COMPLETED,
                    )
                    for order, page_id in enumerate(page_ids, start=1)
                ],
                "matches": [
                    PageMatch(
                        page_id=page_ids[0],
                        page_order=1,
                        page_title="第1页",
                        page_text="课件与大纲存在冲突",
                        selected_outline_ref="outline:1",
                        score=0.9,
                        needs_confirmation=True,
                        conflicts=["课件写4年，大纲写5年"],
                        decision_source="deterministic_rules",
                        candidates=[],
                    )
                ],
            }
        )
    )
    repository = NarrationRepository(service)
    revision_ids = []
    for page_id in page_ids:
        revision = repository.save_revision(
            project.id,
            page_id,
            "本页确认旁白。",
            "规划师",
            expected_revision_id=None,
        )
        revision_ids.append(revision.id)
    return app, project, page_ids, revision_ids


def test_gate_blocks_unconfirmed_pages_and_unresolved_material_conflicts(tmp_path: Path) -> None:
    app, project, page_ids, revision_ids = _ready_project(tmp_path)
    gate = NarrationGateService(app.state.project_service)

    initial = gate.can_enter_audio(project.id)
    assert initial.allowed is False
    assert {reason.code for reason in initial.reasons} == {
        "narration_unconfirmed",
        "material_conflict_unresolved",
    }

    with pytest.raises(ConfirmationError) as unresolved:
        gate.confirm_narration(page_ids[0], revision_ids[0], "规划师", project.id)
    assert unresolved.value.code == "material_conflict_unresolved"

    gate.confirm_narration(
        page_ids[0],
        revision_ids[0],
        "规划师",
        project.id,
        conflict_resolution="保留并列描述，交由观众知悉。",
    )
    gate.confirm_narration(page_ids[1], revision_ids[1], "规划师", project.id)

    completed = gate.can_enter_audio(project.id)
    assert completed.allowed is True
    assert completed.reasons == []


def test_old_revision_cannot_be_confirmed_and_edit_relocks_audio(tmp_path: Path) -> None:
    app, project, page_ids, revision_ids = _ready_project(tmp_path)
    projects = app.state.project_service
    repository = NarrationRepository(projects)
    gate = NarrationGateService(projects)
    newer = repository.save_revision(
        project.id,
        page_ids[0],
        "本页第二版确认旁白。",
        "规划师",
        expected_revision_id=revision_ids[0],
    )

    with pytest.raises(ConfirmationError) as stale:
        gate.confirm_narration(
            page_ids[0],
            revision_ids[0],
            "规划师",
            project.id,
            conflict_resolution="已处理",
        )
    assert stale.value.code == "narration_stale_revision"

    gate.confirm_narration(
        page_ids[0], newer.id, "规划师", project.id, conflict_resolution="已处理"
    )
    gate.confirm_narration(page_ids[1], revision_ids[1], "规划师", project.id)
    assert gate.can_enter_audio(project.id).allowed is True

    repository.save_revision(
        project.id,
        page_ids[0],
        "确认后再次编辑。",
        "规划师",
        expected_revision_id=newer.id,
    )
    relocked = gate.can_enter_audio(project.id)
    assert relocked.allowed is False
    assert any(reason.page_id == page_ids[0] for reason in relocked.reasons)


def test_direct_audio_entry_api_cannot_bypass_confirmation_gate(tmp_path: Path) -> None:
    app, project, _, _ = _ready_project(tmp_path)

    with TestClient(app) as client:
        response = client.post(f"/api/projects/{project.id}/audio/enter")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "narration_gate_blocked"
    assert response.json()["error"]["blocking"] is True


def test_batch_confirmation_is_atomic_when_any_revision_is_invalid(tmp_path: Path) -> None:
    app, project, page_ids, revision_ids = _ready_project(tmp_path)

    with TestClient(app) as client:
        response = client.post(
            f"/api/projects/{project.id}/confirmations/batch",
            json={
                "actor": "规划师",
                "items": [
                    {
                        "page_id": str(page_ids[0]),
                        "revision_id": str(revision_ids[0]),
                        "conflict_resolution": "并列保留冲突信息。",
                    },
                    {"page_id": str(page_ids[1]), "revision_id": str(uuid4())},
                ],
            },
        )

    assert response.status_code == 409
    saved = app.state.project_service.get(project.id)
    assert saved.narration_confirmations == []
    assert all(
        page.narration is not None and page.narration.confirmed_revision_id is None
        for page in saved.pages
    )
