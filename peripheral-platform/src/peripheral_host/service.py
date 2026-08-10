from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from uuid import UUID, uuid4

from peripheral_contracts import (
    ActionRequest,
    ActionType,
    ArtifactRef,
    ErrorDetail,
    JobEnvelope,
    JobResult,
    JobStatus,
    JobStatusResponse,
)

from peripheral_host.artifacts import PublishedArtifact, publish_output, verify_artifact
from peripheral_host.events import EventFactory
from peripheral_host.module_runner import ModuleRegistry
from peripheral_host.repositories import ArtifactRecord, JobRecord, Repositories
from peripheral_host.state_machine import JobStateMachine


class JobNotFound(LookupError):
    pass


class AttemptNotFound(LookupError):
    pass


class InvalidJobAction(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class SubmitResult:
    job_id: UUID
    status: JobStatus
    created: bool


class JobService:
    def __init__(
        self,
        *,
        workspace_root: Path,
        repositories: Repositories,
        registry: ModuleRegistry,
    ) -> None:
        self.workspace_root = workspace_root.resolve()
        self.repositories = repositories
        self.registry = registry
        self.event_factory = EventFactory()
        self.state_machine = JobStateMachine(repositories, event_factory=self.event_factory)

    def submit_job(self, envelope: JobEnvelope) -> SubmitResult:
        registered = self.registry.resolve(envelope.job_type)
        registered.validate_parameters(envelope.parameters)
        for artifact in envelope.inputs:
            verify_artifact(artifact, self.workspace_root)

        database = self.repositories.jobs.database
        with database.transaction(immediate=True) as connection:
            existing = self.repositories.jobs.get_by_idempotency(
                envelope.job_type,
                envelope.idempotency_key,
                connection=connection,
            )
            if existing is not None:
                return SubmitResult(
                    job_id=existing.job_id,
                    status=existing.status,
                    created=False,
                )
            record = self.repositories.jobs.create(envelope, connection=connection)
            accepted = self.event_factory.create(
                record=record,
                event_type="job.accepted",
                data={"progress": 0},
            )
            self.repositories.events.append(accepted, connection=connection)
            return SubmitResult(job_id=record.job_id, status=record.status, created=True)

    def get_job_status(self, job_id: UUID) -> JobStatusResponse:
        return _status_response(self._require_job(job_id))

    def list_artifacts(self, job_id: UUID) -> tuple[ArtifactRecord, ...]:
        self._require_job(job_id)
        return tuple(self.repositories.artifacts.list_for_job(job_id))

    def request_action(
        self,
        job_id: UUID,
        action: ActionRequest,
    ) -> JobStatusResponse:
        record = self._require_job(job_id)
        if action.action is ActionType.CANCEL:
            if record.status in {JobStatus.QUEUED, JobStatus.RETRY_WAIT}:
                updated = self.state_machine.transition(
                    job_id,
                    record.status,
                    JobStatus.CANCELLED,
                    event_data={"requested_by": action.requested_by},
                )
                return _status_response(updated)
            if record.status is JobStatus.RUNNING:
                updated = self.state_machine.transition(
                    job_id,
                    JobStatus.RUNNING,
                    JobStatus.CANCELLING,
                    event_data={"requested_by": action.requested_by},
                )
                return _status_response(updated)
        if action.action is ActionType.RETRY and record.status is JobStatus.FAILED:
            updated = self.state_machine.transition(
                job_id,
                JobStatus.FAILED,
                JobStatus.QUEUED,
                next_attempt_at=None,
                last_error_json=None,
                event_data={"requested_by": action.requested_by},
            )
            return _status_response(updated)
        raise InvalidJobAction(
            f"action {action.action.value} is invalid for state {record.status.value}"
        )

    def complete_attempt(
        self,
        job_id: UUID,
        attempt_id: UUID,
        result: JobResult,
    ) -> JobStatusResponse:
        record = self._require_job(job_id)
        if record.status is not JobStatus.RUNNING:
            raise ValueError("only a running job can complete an attempt")
        if result.job_id != job_id:
            raise ValueError("result job_id does not match job")
        if result.outcome != "succeeded":
            raise ValueError("failed results must be handled by the scheduler")
        attempt = self.repositories.attempts.get(attempt_id)
        if attempt is None or attempt.job_id != job_id:
            raise AttemptNotFound(str(attempt_id))

        published: list[PublishedArtifact] = []
        next_versions: dict[str, int] = {}
        try:
            for output in result.outputs:
                reference = ArtifactRef(
                    artifact_id=uuid4(),
                    kind=output.kind,
                    path=output.staged_path,
                    size_bytes=output.size_bytes,
                    sha256=output.sha256,
                )
                verified = verify_artifact(reference, attempt.root)
                version = next_versions.get(output.logical_name)
                if version is None:
                    version = self.repositories.artifacts.next_version(
                        record.project_id,
                        output.logical_name,
                    )
                next_versions[output.logical_name] = version + 1
                published.append(
                    publish_output(
                        workspace_root=self.workspace_root,
                        attempt_root=attempt.root,
                        staged_path=verified.path,
                        project_id=record.project_id,
                        job_id=job_id,
                        logical_name=output.logical_name,
                        kind=output.kind,
                        version=version,
                    )
                )

            database = self.repositories.jobs.database
            with database.transaction(immediate=True) as connection:
                for artifact in published:
                    stored = self.repositories.artifacts.register_verified(
                        artifact,
                        connection=connection,
                    )
                    for event_type in ("artifact.created", "artifact.verified"):
                        event = self.event_factory.create(
                            record=record,
                            event_type=event_type,
                            data={
                                "artifact_id": str(stored.artifact_id),
                                "logical_name": stored.logical_name,
                                "version": stored.version,
                            },
                        )
                        self.repositories.events.append(event, connection=connection)
                self.repositories.attempts.finish(
                    attempt_id,
                    status="succeeded",
                    exit_code=0,
                    connection=connection,
                )
                updated = self.state_machine.transition(
                    job_id,
                    JobStatus.RUNNING,
                    JobStatus.SUCCEEDED,
                    connection=connection,
                    progress=100,
                )
            return _status_response(updated)
        except Exception:
            self._quarantine_orphans(attempt_id, published)
            raise

    def count_jobs(self) -> int:
        return self.repositories.jobs.count()

    def claim_next(self, now: datetime) -> JobRecord | None:
        database = self.repositories.jobs.database
        with database.transaction(immediate=True) as connection:
            record = self.repositories.jobs.claim_next(now, connection=connection)
            if record is None:
                return None
            started = self.event_factory.create(
                record=record,
                event_type="job.started",
                data={"from": "queued", "to": "running"},
            )
            self.repositories.events.append(started, connection=connection)
            return record

    def requeue_due_retries(self, now: datetime) -> int:
        count = 0
        for record in self.repositories.jobs.list_due_retries(now):
            self.state_machine.transition(
                record.job_id,
                JobStatus.RETRY_WAIT,
                JobStatus.QUEUED,
                next_attempt_at=None,
            )
            count += 1
        return count

    def _require_job(self, job_id: UUID) -> JobRecord:
        record = self.repositories.jobs.get(job_id)
        if record is None:
            raise JobNotFound(str(job_id))
        return record

    def _quarantine_orphans(
        self,
        attempt_id: UUID,
        artifacts: list[PublishedArtifact],
    ) -> None:
        if not artifacts:
            return
        quarantine = self.workspace_root / "quarantine" / "orphaned" / str(attempt_id)
        quarantine.mkdir(parents=True, exist_ok=True)
        for artifact in artifacts:
            if artifact.path.is_file():
                os.replace(
                    artifact.path,
                    quarantine / f"{artifact.artifact_id}-{artifact.path.name}",
                )


def _status_response(record: JobRecord) -> JobStatusResponse:
    error = (
        None
        if record.last_error_json is None
        else ErrorDetail.model_validate_json(record.last_error_json)
    )
    return JobStatusResponse(
        schema_version="1.0",
        job_id=record.job_id,
        project_id=record.project_id,
        job_type=record.envelope.job_type,
        status=record.status,
        attempt_count=record.current_attempt,
        progress=record.progress,
        next_attempt_at=record.next_attempt_at,
        created_at=record.created_at,
        updated_at=record.updated_at,
        error=error,
    )
