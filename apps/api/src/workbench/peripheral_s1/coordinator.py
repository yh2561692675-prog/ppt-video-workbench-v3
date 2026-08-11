from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from peripheral_contracts import BusinessResultManifest
from sqlalchemy import insert, select, update
from workbench_peripheral_adapter.client import PeripheralClientProtocol
from workbench_peripheral_adapter.dto import SubmitJobDto

from workbench.storage.workspace_db import WorkspaceDatabase, peripheral_s1_submissions

from .inbox import ProjectionInbox
from .materializer import materialize_artifact
from .projector import ProjectorRegistry


@dataclass(frozen=True, slots=True)
class JobSpec:
    project_id: UUID
    project_revision: int
    module_id: str
    job_type: str
    affected_page_ids: tuple[UUID, ...]
    inputs: tuple[Any, ...]
    parameters: dict[str, Any]
    runtime_version: str
    requested_by: str
    priority: int = 50
    project_snapshot_sha256: str | None = None


@dataclass(frozen=True, slots=True)
class SubmittedJob:
    job_id: UUID
    idempotency_key: str
    status: str
    created: bool


@dataclass(frozen=True, slots=True)
class ProjectionOutcome:
    status: str
    reason: str | None = None


class S1Coordinator:
    def __init__(
        self,
        *,
        workspace_root: Path,
        adapter: PeripheralClientProtocol,
        inbox: ProjectionInbox | None = None,
        projector: ProjectorRegistry | None = None,
        project_dir_resolver: Callable[[UUID], Path] | None = None,
        database: WorkspaceDatabase | None = None,
    ) -> None:
        self.workspace_root = workspace_root.resolve()
        self.adapter = adapter
        self.inbox = inbox
        self.projector = projector or ProjectorRegistry()
        self.database = database
        self.project_dir_resolver = project_dir_resolver or (
            lambda _project_id: self.workspace_root
        )
        self._submitted: dict[str, SubmittedJob] = {}
        self._specs: dict[UUID, JobSpec] = {}

    def submit(self, spec: JobSpec) -> SubmittedJob:
        spec = self._freeze_project_snapshot(spec)
        key = idempotency_key(spec)
        existing = self._submitted.get(key)
        if existing is None and self.database is not None:
            existing = self._load_submission(key)
        if existing is not None:
            self._submitted[key] = existing
            restored = (
                self._load_spec(existing.job_id) if existing.job_id not in self._specs else None
            )
            if restored is not None:
                self._specs[existing.job_id] = restored
            return SubmittedJob(existing.job_id, key, existing.status, False)
        job_id = uuid4()
        request = SubmitJobDto(
            job_id=job_id,
            project_id=spec.project_id,
            job_type=spec.job_type,
            requested_by=spec.requested_by,
            priority=spec.priority,
            idempotency_key=key,
            inputs=tuple(spec.inputs),
            parameters={
                **spec.parameters,
                "module_id": spec.module_id,
                "project_revision": spec.project_revision,
                "affected_page_ids": [str(item) for item in spec.affected_page_ids],
                "runtime_version": spec.runtime_version,
                "input_fingerprint": input_fingerprint(spec),
                "project_snapshot_sha256": spec.project_snapshot_sha256,
            },
            created_at=datetime.now(UTC),
        )
        result = self.adapter.submit_job(request)
        submitted = SubmittedJob(result.job_id, key, result.status, result.created)
        self._submitted[key] = submitted
        self._specs[result.job_id] = spec
        if self.database is not None:
            with self.database.engine.begin() as connection:
                connection.execute(
                    insert(peripheral_s1_submissions).values(
                        idempotency_key=key,
                        job_id=str(result.job_id),
                        project_id=str(spec.project_id),
                        spec_json=json.dumps(_spec_json(spec), ensure_ascii=False, sort_keys=True),
                        status=result.status,
                        created_at=datetime.now(UTC).isoformat(),
                    )
                )
        return submitted

    def reconcile(self, job_id: UUID) -> ProjectionOutcome:
        spec = self._specs.get(job_id)
        if spec is None:
            spec = self._load_spec(job_id)
            if spec is not None:
                self._specs[job_id] = spec
        if spec is None:
            raise KeyError(str(job_id))
        if self.inbox is None:
            raise RuntimeError("projection inbox is required for reconciliation")
        existing = self.inbox.get(job_id)
        if existing is not None and existing.status == "applied":
            return ProjectionOutcome("already_applied")
        status = self.adapter.get_job_status(job_id)
        self._update_submission_status(job_id, status.status)
        try:
            self._validate_job_status(status, spec)
        except ValueError as error:
            return ProjectionOutcome("quarantined", str(error))
        if status.status != "succeeded":
            return ProjectionOutcome(status.status)
        artifacts = self.adapter.list_artifacts(job_id)
        try:
            self._validate_artifact_ownership(artifacts, job_id, spec.project_id)
        except ValueError as error:
            return ProjectionOutcome("quarantined", str(error))
        result_artifact = next(
            (item for item in artifacts if item.logical_name == "business-result"), None
        )
        if result_artifact is None:
            return ProjectionOutcome("quarantined", "business-result artifact missing")
        pending = self.inbox.ensure_pending(job_id, spec.project_id, result_artifact.sha256)
        if pending.status == "quarantined":
            return ProjectionOutcome("quarantined", pending.reason)
        try:
            project_dir = self.project_dir_resolver(spec.project_id)
            result_path = materialize_artifact(
                self.adapter,
                job_id=job_id,
                artifact=result_artifact,
                project_dir=project_dir,
                destination_name=str(Path(".s1-inbox") / str(job_id) / "business-result.json"),
            )
            business_result = BusinessResultManifest.model_validate_json(result_path.read_bytes())
            self._validate_business_result(business_result, spec)
            self._validate_declared_artifacts(business_result, artifacts)
            self._validate_project_snapshot(project_dir, spec)
            for artifact in artifacts:
                if artifact.logical_name == "business-result":
                    continue
                destination_name = _artifact_destination(
                    business_result.payload,
                    logical_name=artifact.logical_name,
                    sha256=artifact.sha256,
                )
                materialize_artifact(
                    self.adapter,
                    job_id=job_id,
                    artifact=artifact,
                    project_dir=project_dir,
                    destination_name=destination_name,
                )
            self.projector.apply(result_path.read_bytes(), project_dir)
            self.inbox.mark(job_id, "applied")
            return ProjectionOutcome("applied")
        except Exception as error:
            reason = str(error)[:500]
            self.inbox.mark(job_id, "quarantined", reason)
            return ProjectionOutcome("quarantined", reason)

    def _update_submission_status(self, job_id: UUID, status: str) -> None:
        if self.database is None:
            return
        with self.database.engine.begin() as connection:
            connection.execute(
                update(peripheral_s1_submissions)
                .where(peripheral_s1_submissions.c.job_id == str(job_id))
                .values(status=status)
            )

    def _freeze_project_snapshot(self, spec: JobSpec) -> JobSpec:
        if spec.project_snapshot_sha256 is not None:
            return spec
        project_dir = self.project_dir_resolver(spec.project_id)
        manifest_path = project_dir / "project.json"
        if not manifest_path.is_file():
            return spec
        return replace(spec, project_snapshot_sha256=_sha256_file(manifest_path))

    def _validate_project_snapshot(self, project_dir: Path, spec: JobSpec) -> None:
        if spec.project_snapshot_sha256 is None:
            return
        manifest_path = project_dir / "project.json"
        if not manifest_path.is_file():
            raise ValueError("STALE_PROJECT_REVISION: project manifest is missing")
        if _sha256_file(manifest_path) != spec.project_snapshot_sha256:
            raise ValueError("STALE_PROJECT_REVISION: project manifest changed after submission")

    @staticmethod
    def _validate_job_status(status: Any, spec: JobSpec) -> None:
        if status.project_id != spec.project_id or status.job_type != spec.job_type:
            raise ValueError("RESULT_IDENTITY_MISMATCH: job status does not match submission")

    @staticmethod
    def _validate_artifact_ownership(
        artifacts: tuple[Any, ...], job_id: UUID, project_id: UUID
    ) -> None:
        for artifact in artifacts:
            if artifact.job_id != job_id or artifact.project_id != project_id:
                raise ValueError("RESULT_IDENTITY_MISMATCH: artifact ownership mismatch")
            if not artifact.is_current:
                raise ValueError("RESULT_ARTIFACT_MISMATCH: non-current artifact returned")

    @staticmethod
    def _validate_business_result(result: BusinessResultManifest, spec: JobSpec) -> None:
        if (
            result.project_id != spec.project_id
            or result.module_id != spec.module_id.upper()
            or result.job_type != spec.job_type
            or result.project_revision != spec.project_revision
        ):
            raise ValueError("RESULT_IDENTITY_MISMATCH: business result does not match submission")
        if result.input_fingerprint != input_fingerprint(spec):
            raise ValueError("RESULT_INPUT_FINGERPRINT_MISMATCH: business result input changed")

    @staticmethod
    def _validate_declared_artifacts(
        result: BusinessResultManifest, artifacts: tuple[Any, ...]
    ) -> None:
        actual = {
            (item.logical_name, item.kind, item.size_bytes, item.sha256)
            for item in artifacts
            if item.logical_name != "business-result"
        }
        declared = {
            (item.logical_name, item.kind, item.size_bytes, item.sha256)
            for item in result.artifacts
        }
        if actual != declared:
            raise ValueError(
                "RESULT_ARTIFACT_MISMATCH: published artifacts differ from business result"
            )

    def _load_submission(self, key: str) -> SubmittedJob | None:
        if self.database is None:
            return None
        with self.database.connect() as connection:
            row = (
                connection.execute(
                    select(peripheral_s1_submissions).where(
                        peripheral_s1_submissions.c.idempotency_key == key
                    )
                )
                .mappings()
                .first()
            )
        if row is None:
            return None
        return SubmittedJob(UUID(str(row["job_id"])), key, str(row["status"]), False)

    def _load_spec(self, job_id: UUID) -> JobSpec | None:
        if self.database is None:
            return None
        with self.database.connect() as connection:
            row = (
                connection.execute(
                    select(peripheral_s1_submissions).where(
                        peripheral_s1_submissions.c.job_id == str(job_id)
                    )
                )
                .mappings()
                .first()
            )
        if row is None:
            return None
        payload = json.loads(str(row["spec_json"]))
        return JobSpec(
            project_id=UUID(str(payload["project_id"])),
            project_revision=int(payload["project_revision"]),
            module_id=str(payload["module_id"]),
            job_type=str(payload["job_type"]),
            affected_page_ids=tuple(
                UUID(str(item)) for item in payload.get("affected_page_ids", [])
            ),
            inputs=tuple(payload.get("inputs", [])),
            parameters=dict(payload.get("parameters", {})),
            runtime_version=str(payload["runtime_version"]),
            requested_by=str(payload["requested_by"]),
            priority=int(payload.get("priority", 50)),
            project_snapshot_sha256=(
                None
                if payload.get("project_snapshot_sha256") is None
                else str(payload["project_snapshot_sha256"])
            ),
        )


def idempotency_key(spec: JobSpec) -> str:
    payload = _spec_json(spec)
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def input_fingerprint(spec: JobSpec) -> str:
    payload = {
        "project_id": str(spec.project_id),
        "project_revision": spec.project_revision,
        "project_snapshot_sha256": spec.project_snapshot_sha256,
        "module_id": spec.module_id.upper(),
        "job_type": spec.job_type,
        "affected_page_ids": sorted(str(item) for item in spec.affected_page_ids),
        "inputs": [
            item.model_dump(mode="json") if hasattr(item, "model_dump") else item
            for item in spec.inputs
        ],
        "parameters": spec.parameters,
        "runtime_version": spec.runtime_version,
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _spec_json(spec: JobSpec) -> dict[str, Any]:
    return {
        "project_id": str(spec.project_id),
        "project_revision": spec.project_revision,
        "module_id": spec.module_id,
        "job_type": spec.job_type,
        "affected_page_ids": sorted(str(item) for item in spec.affected_page_ids),
        "inputs": [
            item.model_dump(mode="json") if hasattr(item, "model_dump") else item
            for item in spec.inputs
        ],
        "parameters": spec.parameters,
        "runtime_version": spec.runtime_version,
        "requested_by": spec.requested_by,
        "priority": spec.priority,
        "project_snapshot_sha256": spec.project_snapshot_sha256,
    }


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _artifact_destination(payload: object, *, logical_name: str, sha256: str) -> str:
    descriptor = _find_artifact_descriptor(payload, logical_name=logical_name, sha256=sha256)
    if descriptor is None:
        return logical_name
    safe_name = descriptor.get("safe_name")
    if isinstance(safe_name, str):
        return str(Path("01_源文件") / safe_name)
    relative_path = descriptor.get("relative_path")
    return relative_path if isinstance(relative_path, str) else logical_name


def _find_artifact_descriptor(
    value: object, *, logical_name: str, sha256: str
) -> dict[str, object] | None:
    if isinstance(value, dict):
        declared_name = value.get("logical_name")
        if value.get("sha256") == sha256 and (
            declared_name is None or declared_name == logical_name
        ):
            return value
        for child in value.values():
            match = _find_artifact_descriptor(child, logical_name=logical_name, sha256=sha256)
            if match is not None:
                return match
    elif isinstance(value, (list, tuple)):
        for child in value:
            match = _find_artifact_descriptor(child, logical_name=logical_name, sha256=sha256)
            if match is not None:
                return match
    return None
