from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4


def test_p10_preflight_report_blocks_missing_project_materials(tmp_path) -> None:
    from workbench.business_modules.p10_preflight.runner import run_preflight
    from workbench.domain.models import ProjectManifest

    project = ProjectManifest(
        id=uuid4(),
        name="demo",
        project_dir="demo",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    (tmp_path / "demo").mkdir()

    report = run_preflight(project, tmp_path)

    assert report["allowed"] is False
    assert report["issues"]
