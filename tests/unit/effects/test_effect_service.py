from __future__ import annotations

from uuid import uuid4

from workbench.domain.models import PageRecord
from workbench.effects.service import EffectService
from workbench.services.project_service import ProjectService


def test_effect_service_generates_missing_page_without_changing_page_identity(tmp_path) -> None:
    projects = ProjectService(tmp_path)
    try:
        project = projects.create("effects")
        page_id = uuid4()
        projects.save(project.model_copy(update={"pages": [PageRecord(id=page_id, order=1, title="阶段")]}))
        service = EffectService(projects)

        result = service.generate(project.id, page_ids=[page_id])
        saved = projects.get(project.id)

        assert result.changed_page_ids == [page_id]
        assert saved.pages[0].effect_plan is not None
        assert saved.pages[0].id == page_id
    finally:
        projects.close()
