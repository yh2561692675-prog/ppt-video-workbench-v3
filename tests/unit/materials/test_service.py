from __future__ import annotations

from uuid import uuid4

import pytest
from workbench.materials.models import (
    MaterialCollection,
    MaterialCollectionCommand,
    MaterialPageRef,
    MaterialSection,
)
from workbench.materials.service import MaterialCollectionError, MaterialCollectionService


def _collection(project_id):
    section = MaterialSection(order=0, title="第一章")
    page = MaterialPageRef(
        source_ref="slides/1.png", order=0, title="页面一", section_id=section.section_id
    )
    section.page_ids = [page.material_page_id]
    return MaterialCollection(project_id=project_id, sections=[section], page_sequence=[page])


def test_collection_revisions_reorder_and_sync_preview(tmp_path) -> None:
    project_id = uuid4()
    service = MaterialCollectionService(tmp_path, lambda _: "project")
    current = service.create(_collection(project_id))
    page = current.page_sequence[0]
    updated = service.apply(
        project_id,
        MaterialCollectionCommand(
            expected_revision=1,
            kind="disable_page",
            payload={"material_page_id": str(page.material_page_id)},
        ),
    )

    assert updated.revision == 2
    assert updated.content_hash
    preview = service.sync_preview(project_id, timeline_revision=3)
    assert preview.disabled_page_ids == [page.material_page_id]


def test_collection_rejects_stale_revision(tmp_path) -> None:
    project_id = uuid4()
    service = MaterialCollectionService(tmp_path, lambda _: "project")
    service.create(_collection(project_id))
    with pytest.raises(MaterialCollectionError, match="revision"):
        service.apply(
            project_id,
            MaterialCollectionCommand(
                expected_revision=2,
                kind="disable_page",
                payload={"material_page_id": str(uuid4())},
            ),
        )
