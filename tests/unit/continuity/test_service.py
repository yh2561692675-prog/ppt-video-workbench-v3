from __future__ import annotations

from uuid import uuid4

import pytest
from workbench.continuity.models import ContinuityPlanCommand
from workbench.continuity.service import ContinuityConflict, ContinuityService


def test_continuity_commands_are_revisioned_and_persisted(tmp_path):
    project_id = uuid4()
    from_page = uuid4()
    to_page = uuid4()
    service = ContinuityService(tmp_path, project_dir_resolver=lambda _: "project")
    plan = service.create(project_id, duration_ms=5000)
    transition = {
        "from_page_id": str(from_page),
        "to_page_id": str(to_page),
        "kind": "dissolve",
        "duration_ms": 500,
        "audio_mode": "j_cut",
        "audio_offset_ms": 220,
    }
    updated = service.apply(
        project_id,
        ContinuityPlanCommand(
            expected_revision=plan.revision,
            kind="upsert_transition",
            payload={"transition": transition},
        ),
    )
    assert updated.revision == 2
    assert updated.transitions[0].audio_mode == "j_cut"
    assert service.revisions(project_id)[-1].content_hash == updated.content_hash
    with pytest.raises(ContinuityConflict):
        service.apply(
            project_id,
            ContinuityPlanCommand(
                expected_revision=plan.revision,
                kind="remove_transition",
                payload={"transition_id": str(updated.transitions[0].id)},
            ),
        )


def test_overlay_bounds_and_duration_are_checked(tmp_path):
    project_id = uuid4()
    service = ContinuityService(tmp_path, project_dir_resolver=lambda _: "project")
    plan = service.create(project_id, duration_ms=1000)
    with pytest.raises(ValueError):
        service.apply(
            project_id,
            ContinuityPlanCommand(
                expected_revision=plan.revision,
                kind="upsert_overlay",
                payload={
                    "source_ref": "logo.png",
                    "kind": "logo",
                    "start_ms": 900,
                    "duration_ms": 200,
                    "x": 0.8,
                    "y": 0.1,
                    "width": 0.3,
                    "height": 0.2,
                },
            ),
        )
