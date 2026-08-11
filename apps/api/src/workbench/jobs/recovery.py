from __future__ import annotations

from uuid import UUID

from .checkpoint import Checkpoint, CheckpointStore
from .repository import JobRepository


class CheckpointRecovery:
    """Restores only checkpoints that match an already committed DB record."""

    def __init__(self, repository: JobRepository, store: CheckpointStore) -> None:
        self.repository = repository
        self.store = store

    def restore(self, job_id: UUID, *, verify: bool = True) -> Checkpoint | None:
        records = {record.sequence: record for record in self.repository.list_checkpoints(job_id)}
        for checkpoint in self.store.valid_checkpoints(job_id, verify=verify):
            record = records.get(checkpoint.sequence)
            if record is not None and record.checkpoint_hash == self.store.checksum(checkpoint):
                return checkpoint
        return None
