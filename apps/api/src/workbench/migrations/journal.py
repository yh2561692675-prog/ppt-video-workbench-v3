from __future__ import annotations

import json
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class MigrationStage(StrEnum):
    PREPARE = "prepare"
    SNAPSHOT = "snapshot"
    WRITE = "write"
    VALIDATE = "validate"
    COMMIT = "commit"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


class MigrationJournalRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = "1.0"
    project_id: UUID
    plan_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    stage: MigrationStage = MigrationStage.PREPARE
    completed_stages: tuple[MigrationStage, ...] = ()
    checkpoints: dict[str, str] = Field(default_factory=dict)
    error: str | None = Field(default=None, max_length=1000)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class MigrationJournal:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> MigrationJournalRecord | None:
        if not self.path.is_file():
            return None
        return MigrationJournalRecord.model_validate_json(
            self.path.read_text(encoding="utf-8")
        )

    def checkpoint(
        self,
        record: MigrationJournalRecord,
        stage: MigrationStage,
        *,
        error: str | None = None,
    ) -> MigrationJournalRecord:
        completed = list(record.completed_stages)
        if (
            stage not in {MigrationStage.FAILED, MigrationStage.ROLLED_BACK}
            and stage not in completed
        ):
            completed.append(stage)
        now = datetime.now(UTC)
        updated = record.model_copy(
            update={
                "stage": stage,
                "completed_stages": tuple(completed),
                "checkpoints": {**record.checkpoints, stage.value: now.isoformat()},
                "error": error,
                "updated_at": now,
            }
        )
        self._write(updated)
        return updated

    def _write(self, record: MigrationJournalRecord) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(f".{self.path.name}.tmp")
        temporary.write_text(
            json.dumps(record.model_dump(mode="json"), ensure_ascii=False, indent=2)
            + "\n",
            encoding="utf-8",
        )
        temporary.replace(self.path)
