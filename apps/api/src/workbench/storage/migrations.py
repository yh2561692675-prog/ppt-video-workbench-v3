from __future__ import annotations

from collections import defaultdict

from sqlalchemy import text
from sqlalchemy.engine import Connection


class WorkspaceMigrationError(RuntimeError):
    pass


def migrate_v1_to_v2(connection: Connection) -> None:
    columns = {
        str(row[1])
        for row in connection.exec_driver_sql("PRAGMA table_info('jobs')").all()
    }
    additions = {
        "input_fingerprint": "VARCHAR(128)",
        "idempotency_key": "VARCHAR(256)",
        "parent_job_id": "VARCHAR(36)",
        "payload_json": "TEXT",
        "result_json": "TEXT",
        "stage": "VARCHAR(64) NOT NULL DEFAULT 'queued'",
        "message": "VARCHAR(500) NOT NULL DEFAULT ''",
        "error_code": "VARCHAR(96)",
        "revision": "INTEGER NOT NULL DEFAULT 1",
        "heartbeat_at": "VARCHAR(40)",
        "started_at": "VARCHAR(40)",
        "finished_at": "VARCHAR(40)",
    }
    for name, declaration in additions.items():
        if name not in columns:
            connection.exec_driver_sql(f'ALTER TABLE jobs ADD COLUMN "{name}" {declaration}')

    connection.exec_driver_sql(
        "UPDATE jobs SET status = 'queued' WHERE status = 'not_started'"
    )
    connection.exec_driver_sql(
        "UPDATE jobs SET status = 'succeeded' WHERE status = 'completed'"
    )
    connection.exec_driver_sql("UPDATE jobs SET revision = 1 WHERE revision IS NULL")
    connection.exec_driver_sql("UPDATE jobs SET stage = 'queued' WHERE stage IS NULL")
    connection.exec_driver_sql("UPDATE jobs SET message = '' WHERE message IS NULL")

    active_statuses = ("queued", "running", "pause_requested", "paused", "cancel_requested")
    rows = connection.exec_driver_sql(
        """
        SELECT id, project_id, updated_at, created_at
        FROM jobs
        WHERE job_type = 'export_package'
          AND status IN ('queued', 'running', 'pause_requested', 'paused', 'cancel_requested')
        ORDER BY project_id, updated_at DESC, created_at DESC, id DESC
        """
    ).all()
    grouped: dict[str, list[tuple[str, str, str, str]]] = defaultdict(list)
    for row in rows:
        grouped[str(row[1])].append((str(row[0]), str(row[1]), str(row[2]), str(row[3])))
    for project_rows in grouped.values():
        for duplicate in project_rows[1:]:
            connection.execute(
                text(
                    """
                    UPDATE jobs
                    SET status = 'failed',
                        error_code = 'render_job_superseded_during_migration',
                        error = 'superseded during workspace schema migration',
                        finished_at = updated_at,
                        revision = revision + 1
                    WHERE id = :job_id
                    """
                ),
                {"job_id": duplicate[0]},
            )

    connection.exec_driver_sql(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_jobs_active_project_type
        ON jobs(project_id, job_type)
        WHERE job_type = 'export_package'
          AND status IN ('queued', 'running', 'pause_requested', 'paused', 'cancel_requested')
        """
    )
    connection.exec_driver_sql("UPDATE schema_meta SET version = 2 WHERE version = 1")
