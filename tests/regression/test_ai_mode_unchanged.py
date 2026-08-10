from datetime import UTC, datetime
from uuid import uuid4

from workbench.domain.models import ProjectManifest


def test_existing_project_defaults_to_ai_narration() -> None:
    now = datetime.now(UTC)
    project = ProjectManifest(
        id=uuid4(),
        name="旧版 AI 配音项目",
        project_dir="旧版_AI_配音项目",
        created_at=now,
        updated_at=now,
    )

    assert project.presentation_mode == "ai_narration"
    assert project.presenter_timeline is None
