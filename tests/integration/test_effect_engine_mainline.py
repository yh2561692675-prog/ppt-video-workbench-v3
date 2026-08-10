from __future__ import annotations

from uuid import uuid4

from workbench.domain.models import PageRecord
from workbench.effects.service import EffectService
from workbench.services.project_service import ProjectService


def test_effect_plan_round_trip_preserves_page_identity_and_hash(tmp_path) -> None:
    projects = ProjectService(tmp_path)
    try:
        project = projects.create("mainline")
        page_id = uuid4()
        projects.save(
            project.model_copy(
                update={"pages": [PageRecord(id=page_id, order=1, title="第一阶段")]}
            )
        )
        service = EffectService(projects)
        first = service.generate(project.id, page_ids=[page_id])
        loaded = projects.get(project.id)
        record = loaded.pages[0].effect_plan
        assert first.changed_page_ids == [page_id]
        assert record is not None

        second = service.generate(project.id, page_ids=[page_id])

        assert second.skipped_page_ids == [page_id]
        assert projects.get(project.id).pages[0].effect_plan.plan_hash == record.plan_hash
    finally:
        projects.close()
