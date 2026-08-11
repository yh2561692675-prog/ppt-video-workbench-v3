from pathlib import Path

from sqlalchemy import (
    Boolean,
    Column,
    Float,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
    create_engine,
    event,
    insert,
    select,
)
from sqlalchemy.engine import Connection

metadata = MetaData()

schema_meta = Table(
    "schema_meta",
    metadata,
    Column("version", Integer, primary_key=True),
)

projects = Table(
    "projects",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("name", String(120), nullable=False),
    Column("project_dir", String, nullable=False, unique=True),
    Column("manifest_path", String, nullable=False),
    Column("current_step", Integer, nullable=False, default=1),
    Column("status", String(32), nullable=False),
    Column("updated_at", String(40), nullable=False),
)

jobs = Table(
    "jobs",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("project_id", String(36), nullable=False),
    Column("job_type", String(40), nullable=False),
    Column("status", String(32), nullable=False),
    Column("cache_key", String, nullable=False),
    Column("page_id", String(36), nullable=True),
    Column("progress", Float, nullable=False, default=0.0),
    Column("attempts", Integer, nullable=False, default=0),
    Column("max_attempts", Integer, nullable=False),
    Column("paid", Boolean, nullable=False, default=False),
    Column("error", String, nullable=True),
    Column("created_at", String(40), nullable=False),
    Column("updated_at", String(40), nullable=False),
    Column("input_fingerprint", String(128), nullable=True),
    Column("idempotency_key", String(256), nullable=True),
    Column("parent_job_id", String(36), nullable=True),
    Column("payload_json", Text, nullable=True),
    Column("result_json", Text, nullable=True),
    Column("stage", String(64), nullable=False, server_default="queued"),
    Column("message", String(500), nullable=False, server_default=""),
    Column("error_code", String(96), nullable=True),
    Column("revision", Integer, nullable=False, server_default="1"),
    Column("priority", Integer, nullable=False, server_default="0"),
    Column("current_attempt_id", String(36), nullable=True),
    Column("heartbeat_at", String(40), nullable=True),
    Column("started_at", String(40), nullable=True),
    Column("finished_at", String(40), nullable=True),
    UniqueConstraint("project_id", "cache_key", name="uq_jobs_project_cache_key"),
)

job_attempts = Table(
    "job_attempts",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("job_id", String(36), nullable=False),
    Column("generation", Integer, nullable=False),
    Column("status", String(20), nullable=False),
    Column("worker_id", String(120), nullable=True),
    Column("runtime_fingerprint", String(128), nullable=True),
    Column("started_at", String(40), nullable=False),
    Column("heartbeat_at", String(40), nullable=True),
    Column("finished_at", String(40), nullable=True),
    Column("exit_code", Integer, nullable=True),
    Column("error_code", String(96), nullable=True),
    Column("checkpoint_sequence", Integer, nullable=True),
    Column("revision", Integer, nullable=False, server_default="1"),
    UniqueConstraint("job_id", "generation", name="uq_job_attempt_generation"),
)

job_checkpoints = Table(
    "job_checkpoints",
    metadata,
    Column("job_id", String(36), primary_key=True),
    Column("attempt_id", String(36), nullable=False),
    Column("sequence", Integer, primary_key=True),
    Column("checkpoint_json", Text, nullable=False),
    Column("checkpoint_hash", String(64), nullable=False),
    Column("created_at", String(40), nullable=False),
)

artifact_publications = Table(
    "artifact_publications",
    metadata,
    Column("publication_key", String(128), primary_key=True),
    Column("job_id", String(36), nullable=False),
    Column("attempt_id", String(36), nullable=False),
    Column("state", String(20), nullable=False),
    Column("manifest_json", Text, nullable=False),
    Column("manifest_hash", String(64), nullable=False),
    Column("published_at", String(40), nullable=True),
    Column("revision", Integer, nullable=False, server_default="1"),
)

resource_leases = Table(
    "resource_leases",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("job_id", String(36), nullable=False),
    Column("attempt_id", String(36), nullable=False),
    Column("worker_id", String(120), nullable=False),
    Column("generation", Integer, nullable=False),
    Column("cpu_cores", Integer, nullable=False, server_default="0"),
    Column("memory_mb", Integer, nullable=False, server_default="0"),
    Column("gpu_slots", Integer, nullable=False, server_default="0"),
    Column("disk_mb", Integer, nullable=False, server_default="0"),
    Column("status", String(20), nullable=False),
    Column("heartbeat_at", String(40), nullable=False),
    Column("expires_at", String(40), nullable=False),
    Column("revision", Integer, nullable=False, server_default="1"),
)

workers = Table(
    "workers",
    metadata,
    Column("id", String(120), primary_key=True),
    Column("status", String(20), nullable=False),
    Column("runtime_fingerprint", String(128), nullable=False),
    Column("capabilities_json", Text, nullable=False),
    Column("heartbeat_at", String(40), nullable=False),
    Column("revision", Integer, nullable=False, server_default="1"),
)

peripheral_projection_inbox = Table(
    "peripheral_projection_inbox",
    metadata,
    Column("job_id", String(36), primary_key=True),
    Column("project_id", String(36), nullable=False),
    Column("result_sha256", String(64), nullable=False),
    Column("status", String(20), nullable=False),
    Column("reason", String(500), nullable=True),
    Column("created_at", String(40), nullable=False),
    Column("updated_at", String(40), nullable=False),
)

peripheral_s1_submissions = Table(
    "peripheral_s1_submissions",
    metadata,
    Column("idempotency_key", String(64), primary_key=True),
    Column("job_id", String(36), nullable=False, unique=True),
    Column("project_id", String(36), nullable=False),
    Column("spec_json", Text, nullable=False),
    Column("status", String(20), nullable=False),
    Column("created_at", String(40), nullable=False),
)


class WorkspaceDatabase:
    def __init__(self, path: Path) -> None:
        self.path = path.resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(f"sqlite:///{self.path}", future=True)
        event.listen(self.engine, "connect", self._configure_sqlite)

    def initialize(self) -> None:
        metadata.create_all(self.engine)
        with self.engine.begin() as connection:
            version = connection.execute(select(schema_meta.c.version)).scalar_one_or_none()
            if version is None:
                connection.execute(insert(schema_meta).values(version=3))
            elif version == 1:
                from .migrations import migrate_v1_to_v2, migrate_v2_to_v3

                migrate_v1_to_v2(connection)
                migrate_v2_to_v3(connection)
            elif version == 2:
                from .migrations import migrate_v2_to_v3

                migrate_v2_to_v3(connection)
            elif version != 3:
                from .migrations import WorkspaceMigrationError

                raise WorkspaceMigrationError(f"unsupported workspace schema version: {version}")

    def connect(self) -> Connection:
        return self.engine.connect()

    @staticmethod
    def _configure_sqlite(dbapi_connection: object, _: object) -> None:
        cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
        try:
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA foreign_keys=ON")
        finally:
            cursor.close()


def dispose_database(database: WorkspaceDatabase) -> None:
    database.engine.dispose()
