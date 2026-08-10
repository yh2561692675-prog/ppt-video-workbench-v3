from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import insert, select

from workbench.domain.enums import JobStatus, JobType
from workbench.domain.models import JobRecord
from workbench.storage.workspace_db import WorkspaceDatabase, jobs, schema_meta


def _v1_database(path) -> WorkspaceDatabase:
    database = WorkspaceDatabase(path)
    database.initialize()
    with database.engine.begin() as connection:
        connection.exec_driver_sql("UPDATE schema_meta SET version = 1")
    return database


def _insert_v1_job(database: WorkspaceDatabase, *, project_id, cache_key: str, status: str) -> str:
    job_id = uuid4()
    now = datetime.now(UTC).isoformat()
    with database.engine.begin() as connection:
        connection.execute(
            insert(jobs).values(
                id=str(job_id),
                project_id=str(project_id),
                job_type=JobType.EXPORT_PACKAGE.value,
                status=status,
                cache_key=cache_key,
                page_id=None,
                progress=0.2,
                attempts=0,
                max_attempts=3,
                paid=False,
                error=None,
                created_at=now,
                updated_at=now,
            )
        )
    return str(job_id)


def test_initialize_migrates_v1_jobs_and_creates_v2_index(tmp_path) -> None:
    database = _v1_database(tmp_path / "workspace.db")
    project_id = uuid4()
    first_id = _insert_v1_job(database, project_id=project_id, cache_key="first", status="not_started")
    second_id = _insert_v1_job(database, project_id=project_id, cache_key="second", status="completed")

    database.initialize()

    with database.connect() as connection:
        version = connection.execute(select(schema_meta.c.version)).scalar_one()
        rows = connection.execute(select(jobs).order_by(jobs.c.id)).mappings().all()
        index_rows = connection.exec_driver_sql("PRAGMA index_list('jobs')").all()

    assert version == 2
    by_id = {row["id"]: row for row in rows}
    assert by_id[first_id]["status"] == JobStatus.QUEUED.value
    assert by_id[second_id]["status"] == JobStatus.SUCCEEDED.value
    assert by_id[first_id]["revision"] == 1
    assert any(row[1] == "uq_jobs_active_project_type" for row in index_rows)


def test_migration_supersedes_duplicate_active_export_jobs(tmp_path) -> None:
    database = _v1_database(tmp_path / "workspace.db")
    project_id = uuid4()
    older_id = _insert_v1_job(database, project_id=project_id, cache_key="older", status="not_started")
    newer_id = _insert_v1_job(database, project_id=project_id, cache_key="newer", status="running")

    database.initialize()

    with database.connect() as connection:
        rows = connection.execute(select(jobs).where(jobs.c.project_id == str(project_id))).mappings().all()

    by_id = {row["id"]: row for row in rows}
    assert by_id[newer_id]["status"] in {JobStatus.QUEUED.value, JobStatus.RUNNING.value}
    assert by_id[older_id]["status"] == JobStatus.FAILED.value
    assert by_id[older_id]["error_code"] == "render_job_superseded_during_migration"


def test_job_record_accepts_legacy_project_manifest_statuses() -> None:
    payload = {
        "id": uuid4(),
        "project_id": uuid4(),
        "job_type": JobType.EXPORT_PACKAGE.value,
        "status": "completed",
        "cache_key": "legacy",
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
    }

    record = JobRecord.model_validate(payload)

    assert record.status is JobStatus.SUCCEEDED
