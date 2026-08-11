from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import select, update
from sqlalchemy.engine import Connection, RowMapping

from workbench.domain.enums import LeaseStatus, WorkerStatus
from workbench.storage.workspace_db import WorkspaceDatabase, resource_leases, workers

from .contracts import ResourceLeaseRecord, ResourceRequest, WorkerCapability, WorkerRecord


class ResourceLeaseConflict(RuntimeError):
    pass


class ResourceLeaseService:
    def __init__(self, database: WorkspaceDatabase) -> None:
        self.database = database

    def register_worker(
        self,
        worker_id: str,
        *,
        runtime_fingerprint: str,
        capabilities: WorkerCapability,
    ) -> WorkerRecord:
        now = _utc_now()
        with self.database.engine.begin() as connection:
            connection.exec_driver_sql(
                """
                INSERT INTO workers(
                    id, status, runtime_fingerprint, capabilities_json, heartbeat_at, revision
                )
                VALUES (:id, :status, :runtime, :capabilities, :heartbeat, 1)
                ON CONFLICT(id) DO UPDATE SET
                    status = excluded.status,
                    runtime_fingerprint = excluded.runtime_fingerprint,
                    capabilities_json = excluded.capabilities_json,
                    heartbeat_at = excluded.heartbeat_at,
                    revision = workers.revision + 1
                """,
                {
                    "id": worker_id,
                    "status": WorkerStatus.ACTIVE.value,
                    "runtime": runtime_fingerprint,
                    "capabilities": capabilities.model_dump_json(),
                    "heartbeat": now,
                },
            )
            row = (
                connection.execute(select(workers).where(workers.c.id == worker_id))
                .mappings()
                .one()
            )
        return _to_worker(row)

    def heartbeat_worker(self, worker_id: str) -> WorkerRecord:
        now = _utc_now()
        with self.database.engine.begin() as connection:
            result = connection.execute(
                update(workers)
                .where(workers.c.id == worker_id, workers.c.status != WorkerStatus.OFFLINE.value)
                .values(heartbeat_at=now, revision=workers.c.revision + 1)
            )
            if result.rowcount != 1:
                raise ResourceLeaseConflict(f"worker is not active: {worker_id}")
            row = (
                connection.execute(select(workers).where(workers.c.id == worker_id))
                .mappings()
                .one()
            )
        return _to_worker(row)

    def acquire(
        self,
        *,
        job_id: UUID,
        attempt_id: UUID,
        generation: int,
        worker_id: str,
        request: ResourceRequest,
        ttl_seconds: float = 30.0,
    ) -> ResourceLeaseRecord:
        now = datetime.now(UTC)
        expires = now + timedelta(seconds=max(ttl_seconds, 1.0))
        with self.database.engine.begin() as connection:
            worker = (
                connection.execute(select(workers).where(workers.c.id == worker_id))
                .mappings()
                .one_or_none()
            )
            if worker is None or worker["status"] != WorkerStatus.ACTIVE.value:
                raise ResourceLeaseConflict(f"worker is not active: {worker_id}")
            self._reap_expired(connection, now.isoformat())
            lease_id = uuid4()
            connection.execute(
                resource_leases.insert().values(
                    id=str(lease_id),
                    job_id=str(job_id),
                    attempt_id=str(attempt_id),
                    worker_id=worker_id,
                    generation=generation,
                    cpu_cores=request.cpu_cores,
                    memory_mb=request.memory_mb,
                    gpu_slots=request.gpu_slots,
                    disk_mb=request.disk_mb,
                    status=LeaseStatus.ACTIVE.value,
                    heartbeat_at=now.isoformat(),
                    expires_at=expires.isoformat(),
                    revision=1,
                )
            )
            row = (
                connection.execute(
                    select(resource_leases).where(resource_leases.c.id == str(lease_id))
                )
                .mappings()
                .one()
            )
        return _to_lease(row)

    def heartbeat(
        self,
        lease_id: UUID,
        *,
        generation: int,
        ttl_seconds: float = 30.0,
    ) -> ResourceLeaseRecord:
        now = datetime.now(UTC)
        expires = now + timedelta(seconds=max(ttl_seconds, 1.0))
        with self.database.engine.begin() as connection:
            result = connection.execute(
                update(resource_leases)
                .where(
                    resource_leases.c.id == str(lease_id),
                    resource_leases.c.generation == generation,
                    resource_leases.c.status == LeaseStatus.ACTIVE.value,
                )
                .values(
                    heartbeat_at=now.isoformat(),
                    expires_at=expires.isoformat(),
                    revision=resource_leases.c.revision + 1,
                )
            )
            if result.rowcount != 1:
                raise ResourceLeaseConflict("lease is stale or already released")
            row = (
                connection.execute(
                    select(resource_leases).where(resource_leases.c.id == str(lease_id))
                )
                .mappings()
                .one()
            )
        return _to_lease(row)

    def release(self, lease_id: UUID, *, generation: int) -> ResourceLeaseRecord:
        with self.database.engine.begin() as connection:
            result = connection.execute(
                update(resource_leases)
                .where(
                    resource_leases.c.id == str(lease_id),
                    resource_leases.c.generation == generation,
                    resource_leases.c.status == LeaseStatus.ACTIVE.value,
                )
                .values(status=LeaseStatus.RELEASED.value, revision=resource_leases.c.revision + 1)
            )
            if result.rowcount == 0:
                row = (
                    connection.execute(
                        select(resource_leases).where(resource_leases.c.id == str(lease_id))
                    )
                    .mappings()
                    .one_or_none()
                )
                if row is None:
                    raise ResourceLeaseConflict("lease not found")
            row = (
                connection.execute(
                    select(resource_leases).where(resource_leases.c.id == str(lease_id))
                )
                .mappings()
                .one()
            )
        return _to_lease(row)

    def reap_expired(self) -> int:
        with self.database.engine.begin() as connection:
            return self._reap_expired(connection, _utc_now())

    @staticmethod
    def _reap_expired(connection: Connection, now: str) -> int:
        result = connection.execute(
            update(resource_leases)
            .where(
                resource_leases.c.status == LeaseStatus.ACTIVE.value,
                resource_leases.c.expires_at < now,
            )
            .values(status=LeaseStatus.EXPIRED.value, revision=resource_leases.c.revision + 1)
        )
        return int(result.rowcount or 0)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _to_worker(row: RowMapping) -> WorkerRecord:
    payload = dict(row)
    payload["capabilities"] = WorkerCapability.model_validate_json(payload.pop("capabilities_json"))
    return WorkerRecord.model_validate(payload)


def _to_lease(row: RowMapping) -> ResourceLeaseRecord:
    payload = dict(row)
    payload["request"] = ResourceRequest.model_validate(
        {
            "cpu_cores": payload.pop("cpu_cores"),
            "memory_mb": payload.pop("memory_mb"),
            "gpu_slots": payload.pop("gpu_slots"),
            "disk_mb": payload.pop("disk_mb"),
        }
    )
    return ResourceLeaseRecord.model_validate(payload)
