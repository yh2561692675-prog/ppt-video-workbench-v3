from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from workbench.domain.extraction import PageExtraction
from workbench.domain.models import PageRecord, ProjectManifest
from workbench.domain.outline import OutlineBlock, OutlineDocument
from workbench.main import create_app
from workbench.matching.page_matcher import match_outline_to_pages


def test_manual_match_override_is_persisted_and_audited(tmp_path: Path) -> None:
    app = create_app(tmp_path)
    with TestClient(app) as client:
        project_payload = client.post("/api/projects", json={"name": "人工匹配"}).json()["data"]
        project = ProjectManifest.model_validate(project_payload)
        page = PageExtraction(
            id=project.id,
            order=1,
            title="课程体系",
            text="课程体系\n机器学习",
            extraction_method="pptx",
            source_ref="slide:1",
        )
        outline = OutlineDocument(
            source_name="大纲.docx",
            blocks=[
                OutlineBlock(
                    kind="heading", order=1, level=1, text="专业概览", source_ref="paragraph:1"
                ),
                OutlineBlock(
                    kind="heading", order=2, level=1, text="课程体系", source_ref="paragraph:2"
                ),
            ],
        )
        plan = match_outline_to_pages(outline, [page])
        seeded = ProjectManifest.model_validate(
            {
                **project.model_dump(mode="json"),
                "pages": [
                    PageRecord(id=page.id, order=1, title=page.title).model_dump(mode="json")
                ],
                "matches": [match.model_dump(mode="json") for match in plan.matches],
            }
        )
        app.state.project_service.save(seeded)

        response = client.patch(
            f"/api/projects/{project.id}/matches/{page.id}",
            json={"outline_ref": "paragraph:2", "reason": "人工核对课件标题"},
        )

        assert response.status_code == 200
        changed = response.json()["data"]
        assert changed["selected_outline_ref"] == "paragraph:2"
        assert changed["decision_source"] == "manual"
        assert changed["needs_confirmation"] is False
        saved = app.state.project_service.get(project.id)
        assert saved.matches[0].selected_outline_ref == "paragraph:2"
        assert saved.audit_log[-1].action == "page_match_changed"
        assert saved.audit_log[-1].details["reason"] == "人工核对课件标题"
