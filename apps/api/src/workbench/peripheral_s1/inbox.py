from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import insert, select, update

from workbench.storage.workspace_db import WorkspaceDatabase, peripheral_projection_inbox


@dataclass(frozen=True, slots=True)
class InboxRecord:
    job_id: UUID
    project_id: UUID
    result_sha256: str
    status: str
    reason: str | None


class ProjectionInbox:
    def __init__(self, database: WorkspaceDatabase) -> None:
        self.database = database

    def ensure_pending(self, job_id: UUID, project_id: UUID, result_sha256: str) -> InboxRecord:
        now = _now()
        with self.database.engine.begin() as connection:
            existing = (
                connection.execute(
                    select(peripheral_projection_inbox).where(
                        peripheral_projection_inbox.c.job_id == str(job_id)
                    )
                )
                .mappings()
                .first()
            )
            if existing is None:
                connection.execute(
                    insert(peripheral_projection_inbox).values(
                        job_id=str(job_id),
                        project_id=str(project_id),
                        result_sha256=result_sha256,
                        status="pending",
                        reason=None,
                        created_at=now,
                        updated_at=now,
                    )
                )
                return InboxRecord(job_id, project_id, result_sha256, "pending", None)
            record = _record(existing)
            if record.project_id != project_id or record.result_sha256 != result_sha256:
                connection.execute(
                    update(peripheral_projection_inbox)
                    .where(peripheral_projection_inbox.c.job_id == str(job_id))
                    .values(
                        status="quarantined",
                        reason="RESULT_ARTIFACT_MISMATCH: projection identity changed",
                        updated_at=now,
                    )
                )
                return InboxRecord(
                    job_id,
                    project_id,
                    result_sha256,
                    "quarantined",
                    "RESULT_ARTIFACT_MISMATCH: projection identity changed",
                )
            return record

    def get(self, job_id: UUID) -> InboxRecord | None:
        with self.database.connect() as connection:
            row = (
                connection.execute(
                    select(peripheral_projection_inbox).where(
                        peripheral_projection_inbox.c.job_id == str(job_id)
                    )
                )
                .mappings()
                .first()
            )
        return None if row is None else _record(row)

    def mark(self, job_id: UUID, status: str, reason: str | None = None) -> InboxRecord:
        if status not in {"pending", "applied", "quarantined"}:
            raise ValueError(f"invalid inbox status: {status}")
        with self.database.engine.begin() as connection:
            connection.execute(
                update(peripheral_projection_inbox)
                .where(peripheral_projection_inbox.c.job_id == str(job_id))
                .values(status=status, reason=reason, updated_at=_now())
            )
            row = (
                connection.execute(
                    select(peripheral_projection_inbox).where(
                        peripheral_projection_inbox.c.job_id == str(job_id)
                    )
                )
                .mappings()
                .first()
            )
        if row is None:
            raise KeyError(str(job_id))
        return _record(row)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _record(row: Any) -> InboxRecord:
    mapping = row
    return InboxRecord(
        job_id=UUID(str(mapping["job_id"])),
        project_id=UUID(str(mapping["project_id"])),
        result_sha256=str(mapping["result_sha256"]),
        status=str(mapping["status"]),
        reason=None if mapping["reason"] is None else str(mapping["reason"]),
    )
