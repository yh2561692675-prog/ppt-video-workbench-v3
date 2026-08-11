from __future__ import annotations

from collections import defaultdict

from sqlalchemy import text
from sqlalchemy.engine import Connection


class WorkspaceMigrationError(RuntimeError):
    pass


def migrate_v1_to_v2(connection: Connection) -> None:
    columns = {str(row[1]) for row in connection.exec_driver_sql("PRAGMA table_info('jobs')").all()}
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
        "priority": "INTEGER NOT NULL DEFAULT 0",
        "current_attempt_id": "VARCHAR(36)",
        "heartbeat_at": "VARCHAR(40)",
        "started_at": "VARCHAR(40)",
        "finished_at": "VARCHAR(40)",
    }
    for name, declaration in additions.items():
        if name not in columns:
            connection.exec_driver_sql(f'ALTER TABLE jobs ADD COLUMN "{name}" {declaration}')

    connection.exec_driver_sql("UPDATE jobs SET status = 'queued' WHERE status = 'not_started'")
    connection.exec_driver_sql("UPDATE jobs SET status = 'succeeded' WHERE status = 'completed'")
    connection.exec_driver_sql("UPDATE jobs SET revision = 1 WHERE revision IS NULL")
    connection.exec_driver_sql("UPDATE jobs SET stage = 'queued' WHERE stage IS NULL")
    connection.exec_driver_sql("UPDATE jobs SET message = '' WHERE message IS NULL")

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


def migrate_v2_to_v3(connection: Connection) -> None:
    """Add durable attempt, checkpoint, publication, lease and worker tables."""

    connection.exec_driver_sql(
        """
        CREATE TABLE IF NOT EXISTS job_attempts (
            id VARCHAR(36) PRIMARY KEY,
            job_id VARCHAR(36) NOT NULL,
            generation INTEGER NOT NULL,
            status VARCHAR(20) NOT NULL,
            worker_id VARCHAR(120),
            runtime_fingerprint VARCHAR(128),
            started_at VARCHAR(40) NOT NULL,
            heartbeat_at VARCHAR(40),
            finished_at VARCHAR(40),
            exit_code INTEGER,
            error_code VARCHAR(96),
            checkpoint_sequence INTEGER,
            revision INTEGER NOT NULL DEFAULT 1,
            CONSTRAINT uq_job_attempt_generation UNIQUE (job_id, generation)
        )
        """
    )
    connection.exec_driver_sql(
        """
        CREATE TABLE IF NOT EXISTS job_checkpoints (
            job_id VARCHAR(36) NOT NULL,
            attempt_id VARCHAR(36) NOT NULL,
            sequence INTEGER NOT NULL,
            checkpoint_json TEXT NOT NULL,
            checkpoint_hash VARCHAR(64) NOT NULL,
            created_at VARCHAR(40) NOT NULL,
            PRIMARY KEY (job_id, sequence)
        )
        """
    )
    connection.exec_driver_sql(
        """
        CREATE TABLE IF NOT EXISTS artifact_publications (
            publication_key VARCHAR(128) PRIMARY KEY,
            job_id VARCHAR(36) NOT NULL,
            attempt_id VARCHAR(36) NOT NULL,
            state VARCHAR(20) NOT NULL,
            manifest_json TEXT NOT NULL,
            manifest_hash VARCHAR(64) NOT NULL,
            published_at VARCHAR(40),
            revision INTEGER NOT NULL DEFAULT 1
        )
        """
    )
    connection.exec_driver_sql(
        """
        CREATE TABLE IF NOT EXISTS resource_leases (
            id VARCHAR(36) PRIMARY KEY,
            job_id VARCHAR(36) NOT NULL,
            attempt_id VARCHAR(36) NOT NULL,
            worker_id VARCHAR(120) NOT NULL,
            generation INTEGER NOT NULL,
            cpu_cores INTEGER NOT NULL DEFAULT 0,
            memory_mb INTEGER NOT NULL DEFAULT 0,
            gpu_slots INTEGER NOT NULL DEFAULT 0,
            disk_mb INTEGER NOT NULL DEFAULT 0,
            status VARCHAR(20) NOT NULL,
            heartbeat_at VARCHAR(40) NOT NULL,
            expires_at VARCHAR(40) NOT NULL,
            revision INTEGER NOT NULL DEFAULT 1
        )
        """
    )
    connection.exec_driver_sql(
        """
        CREATE TABLE IF NOT EXISTS workers (
            id VARCHAR(120) PRIMARY KEY,
            status VARCHAR(20) NOT NULL,
            runtime_fingerprint VARCHAR(128) NOT NULL,
            capabilities_json TEXT NOT NULL,
            heartbeat_at VARCHAR(40) NOT NULL,
            revision INTEGER NOT NULL DEFAULT 1
        )
        """
    )
    connection.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS ix_job_attempts_job_status ON job_attempts(job_id, status)"
    )
    connection.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS ix_resource_leases_active "
        "ON resource_leases(status, expires_at)"
    )
    connection.exec_driver_sql("UPDATE schema_meta SET version = 3 WHERE version = 2")


def migrate_v3_to_v4(connection: Connection) -> None:
    """Add the persistent cache entry and reverse dependency index."""

    connection.exec_driver_sql(
        """
        CREATE TABLE IF NOT EXISTS cache_entries (
            cache_key VARCHAR(64) PRIMARY KEY,
            project_id VARCHAR(36) NOT NULL,
            domain VARCHAR(40) NOT NULL,
            node_key VARCHAR(240) NOT NULL,
            state VARCHAR(20) NOT NULL,
            artifact_manifest_json TEXT NOT NULL,
            artifact_manifest_hash VARCHAR(64) NOT NULL,
            relative_path VARCHAR(500) NOT NULL,
            artifact_hash VARCHAR(64) NOT NULL,
            size_bytes INTEGER NOT NULL,
            runtime_fingerprint VARCHAR(128) NOT NULL,
            license_status VARCHAR(24) NOT NULL,
            rebuildable BOOLEAN NOT NULL DEFAULT 1,
            protected BOOLEAN NOT NULL DEFAULT 0,
            lease_count INTEGER NOT NULL DEFAULT 0,
            stale_reason VARCHAR(80),
            created_at VARCHAR(40) NOT NULL,
            last_accessed_at VARCHAR(40) NOT NULL,
            revision INTEGER NOT NULL DEFAULT 1
        )
        """
    )
    connection.exec_driver_sql(
        """
        CREATE TABLE IF NOT EXISTS cache_dependencies (
            dependency_key VARCHAR(64) NOT NULL,
            cache_key VARCHAR(64) NOT NULL,
            domain VARCHAR(40) NOT NULL,
            node_key VARCHAR(240) NOT NULL,
            upstream_kind VARCHAR(80) NOT NULL,
            upstream_key VARCHAR(500) NOT NULL,
            upstream_hash VARCHAR(64) NOT NULL,
            start_us INTEGER,
            end_us INTEGER,
            artifact_refs_json TEXT NOT NULL,
            PRIMARY KEY (cache_key, dependency_key)
        )
        """
    )
    connection.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS ix_cache_dependencies_upstream "
        "ON cache_dependencies(upstream_kind, upstream_key, domain)"
    )
    connection.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS ix_cache_dependencies_cache_key "
        "ON cache_dependencies(cache_key)"
    )
    connection.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS ix_cache_entries_project_state "
        "ON cache_entries(project_id, state, last_accessed_at)"
    )
    connection.exec_driver_sql("UPDATE schema_meta SET version = 4 WHERE version = 3")
