from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest

PLATFORM_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PLATFORM_ROOT / "src"
REPOSITORY_ROOT = PLATFORM_ROOT.parent
WORKBENCH_SRC_ROOT = REPOSITORY_ROOT / "apps" / "api" / "src"

for source_root in (SRC_ROOT, WORKBENCH_SRC_ROOT):
    if str(source_root) not in sys.path:
        sys.path.insert(0, str(source_root))


from peripheral_contracts import JobEnvelope  # noqa: E402


@pytest.fixture
def job() -> JobEnvelope:
    return JobEnvelope(
        schema_version="1.0",
        job_id=uuid4(),
        project_id=uuid4(),
        job_type="system.echo",
        requested_by="workbench",
        priority=50,
        idempotency_key=uuid4().hex,
        parameters={"text": "repository test"},
        created_at=datetime.now(UTC),
    )
