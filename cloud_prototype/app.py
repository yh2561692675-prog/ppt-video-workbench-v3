from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import tempfile
import threading
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal, cast
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from fastapi import APIRouter, FastAPI, Header, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from workbench.contracts.p2_platform import BudgetV1, canonical_sha256


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _expires(seconds: int) -> str:
    return (datetime.now(UTC) + timedelta(seconds=seconds)).isoformat().replace("+00:00", "Z")


def _timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _token_hash(token: str) -> str:
    return f"sha256:{hashlib.sha256(token.encode()).hexdigest()}"


def _principal_id(actor_id: str) -> str:
    try:
        return str(UUID(actor_id))
    except ValueError:
        return str(uuid5(NAMESPACE_URL, f"ppt-video-workbench:cloud-principal:{actor_id}"))


_SENSITIVE_KEYS = {
    "api_key",
    "apikey",
    "authorization",
    "cookie",
    "password",
    "secret",
    "token",
}
_PATH_KEYS = {
    "path",
    "source_path",
    "file",
    "file_path",
    "directory",
    "directory_path",
    "executable_ref",
}


def _assert_portable_document(value: object, *, field: str = "document") -> None:
    """Reject secrets and host paths before a manifest enters a cloud revision."""

    if isinstance(value, dict):
        for key, item in value.items():
            normalized_key = str(key).lower()
            if normalized_key in _SENSITIVE_KEYS or any(
                marker in normalized_key for marker in ("api_key", "authorization", "password")
            ):
                raise HTTPException(status_code=422, detail="sensitive_field_rejected")
            _assert_portable_document(item, field=f"{field}.{key}")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _assert_portable_document(item, field=f"{field}[{index}]")
        return
    if not isinstance(value, str):
        return
    lowered = field.lower()
    key = lowered.rsplit(".", 1)[-1].rsplit("]", 1)[-1]
    if key not in _PATH_KEYS and not lowered.endswith(
        ("path", "_path", "file", "_file", "directory", "_dir")
    ):
        return
    if value.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:[\\/]", value):
        raise HTTPException(status_code=422, detail="absolute_path_rejected")
    if value.startswith("../") or value.startswith("..\\") or value == "..":
        raise HTTPException(status_code=422, detail="path_escape_rejected")


def _validate_uploaded_content(media_type: str, content: bytes) -> None:
    """Apply small deterministic container checks in the local object gateway."""

    lowered = media_type.lower()
    if lowered == "image/png" and not content.startswith(b"\x89PNG\r\n\x1a\n"):
        raise HTTPException(status_code=422, detail="content_type_mismatch")
    if lowered == "application/pdf" and not content.startswith(b"%PDF-"):
        raise HTTPException(status_code=422, detail="content_type_mismatch")
    if lowered in {"audio/wav", "audio/x-wav"} and not (
        content.startswith(b"RIFF") and content[8:12] == b"WAVE"
    ):
        raise HTTPException(status_code=422, detail="content_type_mismatch")
    if lowered == "video/mp4" and b"ftyp" not in content[:64]:
        raise HTTPException(status_code=422, detail="content_type_mismatch")
    if lowered in {"text/html", "application/xhtml+xml"} and b"<script" in content.lower():
        raise HTTPException(status_code=422, detail="malicious_content_rejected")


class CloudModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


_FINGERPRINT_KEY = re.compile(r"^[a-z][a-z0-9_.-]{0,63}$")
_FINGERPRINT_VALUE = re.compile(r"^sha256:[0-9a-f]{64}$")
_REMOTE_FINGERPRINT_KEYS = {"provider_policy", "runtime", "platform", "input"}


def _validate_fingerprints(value: dict[str, str]) -> dict[str, str]:
    if any(not _FINGERPRINT_KEY.fullmatch(key) for key in value):
        raise ValueError("fingerprint keys must be lowercase contract identifiers")
    if any(not _FINGERPRINT_VALUE.fullmatch(item) for item in value.values()):
        raise ValueError("fingerprints must be sha256 references")
    return dict(value)


def _validate_remote_fingerprints(value: dict[str, str]) -> dict[str, str]:
    validated = _validate_fingerprints(value)
    missing = _REMOTE_FINGERPRINT_KEYS - set(validated)
    if missing:
        raise ValueError(f"remote execution fingerprints missing: {', '.join(sorted(missing))}")
    return validated


def _sync_target_keys(kind: str, payload: dict[str, Any]) -> list[str]:
    explicit = payload.get("targets")
    if explicit is not None:
        if not isinstance(explicit, list) or any(
            not isinstance(item, str)
            or not item
            or len(item) > 256
            or not re.fullmatch(r"[a-z][a-z0-9_.-]*:[A-Za-z0-9_.:@/-]+", item)
            for item in explicit
        ):
            raise HTTPException(status_code=422, detail="invalid_sync_targets")
        return sorted(set(explicit))
    identity_fields = (
        ("clip_id", "clip"),
        ("asset_id", "asset"),
        ("page_id", "page"),
        ("material_id", "material"),
    )
    targets = [
        f"{prefix}:{payload[field]}"
        for field, prefix in identity_fields
        if payload.get(field)
    ]
    if kind == "project.metadata.set":
        metadata = payload.get("metadata")
        if isinstance(metadata, dict):
            targets.extend(f"project.metadata:{key}" for key in metadata)
        else:
            targets.extend(
                f"project.metadata:{key}"
                for key in payload
                if key not in {"targets", "client_note"}
            )
    if kind == "page.move":
        targets.append("page-order:root")
    if not targets:
        targets.append(f"{kind}:root")
    if any(len(item) > 256 for item in targets):
        raise HTTPException(status_code=422, detail="invalid_sync_targets")
    return sorted(set(targets))


def _sync_conflict_kind(
    incoming_kind: str, incoming_targets: set[str], intervening: list[tuple[str, set[str]]]
) -> str:
    if "page-order:root" in incoming_targets:
        return "page_order"
    if incoming_kind.endswith(".remove") or any(
        kind.endswith(".remove") and incoming_targets & targets for kind, targets in intervening
    ):
        return "delete_modify"
    return "same_field"


def _apply_sync_operation(
    manifest: dict[str, Any], kind: str, payload: dict[str, Any], targets: list[str]
) -> dict[str, Any]:
    updated = cast(dict[str, Any], json.loads(json.dumps(manifest, ensure_ascii=False)))
    objects = updated.setdefault("sync_objects", {})
    if not isinstance(objects, dict):
        raise HTTPException(status_code=409, detail="incompatible_sync_manifest")
    if kind == "project.metadata.set":
        metadata = updated.setdefault("metadata", {})
        if not isinstance(metadata, dict):
            raise HTTPException(status_code=409, detail="incompatible_sync_manifest")
        metadata_values = payload.get("metadata")
        values: dict[str, Any] = metadata_values if isinstance(metadata_values, dict) else payload
        for key, value in values.items():
            if key not in {"targets", "client_note"}:
                metadata[str(key)] = value
    for target in targets:
        if kind.endswith(".remove"):
            objects.pop(target, None)
        else:
            objects[target] = {"kind": kind, "payload": payload}
    updated["last_operation"] = {"kind": kind, "payload": payload, "targets": targets}
    return updated


class WorkspaceCreate(CloudModel):
    name: str = Field(min_length=1, max_length=120)
    organization_id: UUID | None = None


class OrganizationCreate(CloudModel):
    name: str = Field(min_length=1, max_length=200)


class MemberAdd(CloudModel):
    actor_id: str = Field(min_length=1, max_length=200)
    role: Literal["admin", "editor", "reviewer", "viewer"] = "editor"


class DeviceRegister(CloudModel):
    device_id: UUID = Field(default_factory=uuid4)
    name: str = Field(min_length=1, max_length=200)
    platform: Literal["windows", "macos", "linux"]


class ServiceAccountCreate(CloudModel):
    name: str = Field(min_length=1, max_length=200)


class ProjectCreate(CloudModel):
    name: str = Field(min_length=1, max_length=200)
    manifest: dict[str, Any] = Field(default_factory=dict)


class SyncOperation(CloudModel):
    schema_version: Literal[1] = 1
    operation_id: UUID
    idempotency_key: UUID
    attempt_id: UUID
    workspace_id: UUID
    project_id: UUID
    base_revision_id: UUID
    client_id: UUID
    client_sequence: int = Field(ge=0)
    kind: Literal[
        "project.metadata.set",
        "material.add",
        "material.remove",
        "page.insert",
        "page.move",
        "page.replace",
        "page.remove",
        "timeline.patch",
        "revision.resolve_conflict",
    ]
    payload: dict[str, Any]
    payload_sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    created_at: str = Field(min_length=1, max_length=80)


class SyncConflictResolution(CloudModel):
    expected_head_revision_id: UUID
    strategy: Literal["keep_remote", "apply_local", "merged"]
    merged_payload: dict[str, Any] | None = None
    reason: str = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def validate_merged_payload(self) -> SyncConflictResolution:
        if self.strategy == "merged" and self.merged_payload is None:
            raise ValueError("merged strategy requires merged_payload")
        if self.strategy != "merged" and self.merged_payload is not None:
            raise ValueError("merged_payload is only valid for merged strategy")
        return self


class InitiateUpload(CloudModel):
    object: dict[str, Any]


class CompleteUpload(CloudModel):
    parts: list[dict[str, Any]] = Field(min_length=1, max_length=10000)


class CommentAnchorModel(CloudModel):
    revision_id: UUID
    logical_path: str | None = Field(default=None, min_length=1, max_length=1024)
    page_id: UUID | None = None
    clip_id: UUID | None = None
    time_ms: int | None = Field(default=None, ge=0)
    end_time_ms: int | None = Field(default=None, ge=0)
    evidence_object_id: str | None = Field(
        default=None, pattern=r"^sha256:[0-9a-f]{64}$"
    )

    @model_validator(mode="after")
    def validate_time_range(self) -> CommentAnchorModel:
        if self.end_time_ms is not None and self.time_ms is None:
            raise ValueError("end_time_ms requires time_ms")
        if (
            self.time_ms is not None
            and self.end_time_ms is not None
            and self.end_time_ms < self.time_ms
        ):
            raise ValueError("end_time_ms must not precede time_ms")
        return self


class CommentCreate(CloudModel):
    body: str = Field(min_length=1, max_length=10000)
    anchor: CommentAnchorModel


class ReviewCreate(CloudModel):
    revision_id: UUID
    content_sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    decision: Literal["approved", "changes_requested"]
    note: str | None = Field(default=None, max_length=10000)


class LeaseRequest(CloudModel):
    client_id: UUID
    base_revision_id: UUID
    scope: Literal["project_edit", "timeline_edit", "review"] = "project_edit"
    lease_id: UUID | None = None
    requested_ttl_seconds: int = Field(ge=30, le=900)


class JobCreate(CloudModel):
    revision_id: UUID
    kind: Literal["render", "transcribe", "export"]
    provider_policy_sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    provider_budget: BudgetV1
    provider_cost_estimate_minor: int = Field(ge=0, le=10_000_000_000)
    runtime_image_sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    required_capabilities: list[str] = Field(default_factory=list, max_length=100)
    required_region: str | None = Field(default=None, min_length=1, max_length=64)
    parameters: dict[str, Any] = Field(default_factory=dict)
    fingerprints: dict[str, str] = Field(max_length=16)

    _fingerprints = field_validator("fingerprints")(_validate_remote_fingerprints)

    @field_validator("required_capabilities")
    @classmethod
    def validate_required_capabilities(cls, value: list[str]) -> list[str]:
        if any(not item or len(item) > 128 for item in value):
            raise ValueError("capability labels must contain 1-128 characters")
        return sorted(set(value))

    @model_validator(mode="after")
    def validate_provider_budget(self) -> JobCreate:
        maximum = self.provider_budget.max_cost_minor
        if maximum is None:
            raise ValueError("remote provider jobs require max_cost_minor")
        if self.provider_cost_estimate_minor > maximum:
            raise ValueError("provider cost estimate exceeds budget")
        return self


class JobClaimRequest(CloudModel):
    executor_id: UUID
    requested_ttl_seconds: int = Field(default=120, ge=30, le=900)


class JobResultReport(CloudModel):
    attempt_id: UUID
    executor_id: UUID
    status: Literal["completed", "failed"]
    result_schema_version: Literal[1]
    result: dict[str, Any] = Field(default_factory=dict)
    result_sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    output_refs: list[str] = Field(default_factory=list, max_length=1000)
    output_media_types: dict[str, str] = Field(default_factory=dict, max_length=1000)
    fingerprints: dict[str, str] = Field(max_length=16)

    _fingerprints = field_validator("fingerprints")(_validate_remote_fingerprints)

    @model_validator(mode="after")
    def validate_output_manifest(self) -> JobResultReport:
        if len(set(self.output_refs)) != len(self.output_refs):
            raise ValueError("output_refs must be unique")
        if any(
            not media_type or len(media_type) > 255
            for media_type in self.output_media_types.values()
        ):
            raise ValueError("output media types must contain 1-255 characters")
        return self


class ExecutorRegister(CloudModel):
    executor_id: UUID = Field(default_factory=uuid4)
    platform: Literal["windows", "macos", "linux"]
    capabilities: list[str] = Field(min_length=1, max_length=100)
    region: str = Field(min_length=1, max_length=64)
    gpu_label: str | None = Field(default=None, min_length=1, max_length=128)
    office_capability: Literal["microsoft_office", "libreoffice", "none"] = "none"
    ttl_seconds: int = Field(default=120, ge=30, le=900)
    capability_snapshot: dict[str, Any] = Field(default_factory=dict, max_length=128)

    @field_validator("capabilities")
    @classmethod
    def validate_capabilities(cls, value: list[str]) -> list[str]:
        if any(not item or len(item) > 128 for item in value):
            raise ValueError("capability labels must contain 1-128 characters")
        return sorted(set(value))


@dataclass(frozen=True)
class CloudAuthConfig:
    mode: Literal["development", "production"] = "development"
    oidc_issuer: str | None = None
    oidc_audience: str | None = None

    @property
    def production_ready(self) -> bool:
        return self.mode == "production" and bool(self.oidc_issuer and self.oidc_audience)


@dataclass(frozen=True)
class CloudProductionEvidence:
    """Release evidence that must be supplied before production auth can open."""

    oidc_validation: bool = False
    postgres_pitr_restore: bool = False
    object_retention_and_export: bool = False
    security_scans: bool = False
    data_residency_and_slo: bool = False
    executor_result_verification: bool = False

    def missing(self) -> list[str]:
        return [
            field_name
            for field_name, present in (
                ("oidc_validation", self.oidc_validation),
                ("postgres_pitr_restore", self.postgres_pitr_restore),
                ("object_retention_and_export", self.object_retention_and_export),
                ("security_scans", self.security_scans),
                ("data_residency_and_slo", self.data_residency_and_slo),
                ("executor_result_verification", self.executor_result_verification),
            )
            if not present
        ]

    @property
    def ready(self) -> bool:
        return not self.missing()


class CloudRepository:
    """Small SQLite WAL repository with tenant checks in every project query."""

    def __init__(
        self,
        db_path: Path,
        object_root: Path,
        *,
        migration_root: Path | None = None,
    ) -> None:
        self.db_path = db_path
        self.object_root = object_root
        self.migration_root = migration_root or Path(__file__).with_name("migrations")
        self.object_root.mkdir(parents=True, exist_ok=True)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    def _object_path(self, project_id: str, object_id: str) -> Path:
        """Resolve a content-addressed object only at the storage edge.

        The database stores a logical storage key, never an absolute host path.
        This keeps exports, logs and sync payloads portable across machines.
        """

        digest = object_id.removeprefix("sha256:")
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise HTTPException(status_code=422, detail="invalid_object_id")
        root = self.object_root.resolve()
        candidate = (root / project_id / digest).resolve()
        try:
            candidate.relative_to(root)
        except ValueError as error:
            raise HTTPException(status_code=422, detail="invalid_object_path") from error
        return candidate

    def _init_db(self) -> None:
        with self._connect() as db:
            db.execute("PRAGMA journal_mode = WAL")
            db.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations ("
                "version INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL, "
                "checksum TEXT NOT NULL, applied_at TEXT NOT NULL)"
            )
            db.commit()
            self._apply_migrations(db)
            self._upgrade_legacy_columns(db)

    def _apply_migrations(self, db: sqlite3.Connection) -> None:
        if not self.migration_root.is_dir():
            raise RuntimeError(f"cloud migration directory is missing: {self.migration_root}")
        migration_files: dict[int, Path] = {}
        for path in sorted(self.migration_root.glob("*.sql")):
            match = re.fullmatch(r"(\d{4})_([a-z0-9_]+)\.sql", path.name)
            if match is None:
                raise RuntimeError(f"invalid cloud migration filename: {path.name}")
            version = int(match.group(1))
            if version in migration_files:
                raise RuntimeError(f"duplicate cloud migration version: {version}")
            migration_files[version] = path
        if not migration_files:
            raise RuntimeError("no cloud database migrations were found")
        expected_versions = list(range(1, max(migration_files) + 1))
        if sorted(migration_files) != expected_versions:
            raise RuntimeError("cloud database migration versions must be contiguous")

        applied = {
            int(row["version"]): row
            for row in db.execute(
                "SELECT version, name, checksum FROM schema_migrations ORDER BY version"
            )
        }
        unknown_versions = sorted(set(applied) - set(migration_files))
        if unknown_versions:
            raise RuntimeError(
                f"cloud database is newer than this runtime: versions={unknown_versions}"
            )

        for version, path in migration_files.items():
            migration_text = path.read_text(encoding="utf-8")
            migration_text = migration_text.replace("\r\n", "\n").replace("\r", "\n")
            checksum = f"sha256:{hashlib.sha256(migration_text.encode()).hexdigest()}"
            existing = applied.get(version)
            if existing is not None:
                if existing["name"] != path.stem or existing["checksum"] != checksum:
                    raise RuntimeError(f"cloud migration checksum mismatch: {path.name}")
                continue
            statements = [statement.strip() for statement in migration_text.split(";")]
            db.execute("BEGIN IMMEDIATE")
            try:
                for statement in statements:
                    if statement:
                        db.execute(statement)
                db.execute(
                    "INSERT INTO schema_migrations (version, name, checksum, applied_at) "
                    "VALUES (?, ?, ?, ?)",
                    (version, path.stem, checksum, _now()),
                )
            except Exception:
                db.rollback()
                raise
            else:
                db.commit()

    @staticmethod
    def _upgrade_legacy_columns(db: sqlite3.Connection) -> None:
        columns = {row["name"] for row in db.execute("PRAGMA table_info(jobs)")}
        job_columns = {
            "executor_id": "TEXT",
            "fingerprints_json": "TEXT NOT NULL DEFAULT '{}'",
            "attempt_id": "TEXT",
            "lease_id": "TEXT",
            "lease_expires_at": "TEXT",
            "attempt_count": "INTEGER NOT NULL DEFAULT 0",
            "attempt_token_hash": "TEXT",
            "attempt_token_expires_at": "TEXT",
            "provider_policy_sha256": (
                "TEXT NOT NULL DEFAULT "
                "'sha256:0000000000000000000000000000000000000000000000000000000000000000'"
            ),
            "provider_budget_json": (
                "TEXT NOT NULL DEFAULT "
                "'{\"schema_version\":1,\"timeout_ms\":86400000,\"max_attempts\":1,"
                "\"max_input_bytes\":1073741824,\"max_output_bytes\":4294967296,"
                "\"max_cost_minor\":0}'"
            ),
            "provider_cost_estimate_minor": "INTEGER NOT NULL DEFAULT 0",
            "runtime_image_sha256": (
                "TEXT NOT NULL DEFAULT "
                "'sha256:0000000000000000000000000000000000000000000000000000000000000000'"
            ),
            "required_capabilities_json": "TEXT NOT NULL DEFAULT '[]'",
            "required_region": "TEXT",
            "idempotency_key": "TEXT",
            "request_sha256": "TEXT",
            "claim_idempotency_key": "TEXT",
        }
        for name, declaration in job_columns.items():
            if name not in columns:
                db.execute(f"ALTER TABLE jobs ADD COLUMN {name} {declaration}")
        db.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS jobs_project_idempotency_key "
            "ON jobs(project_id, idempotency_key) WHERE idempotency_key IS NOT NULL"
        )
        result_columns = {
            row["name"] for row in db.execute("PRAGMA table_info(job_results)")
        }
        job_result_columns = {
            "output_refs_json": "TEXT NOT NULL DEFAULT '[]'",
            "fingerprints_json": "TEXT NOT NULL DEFAULT '{}'",
            "result_schema_version": "INTEGER NOT NULL DEFAULT 1",
            "output_media_types_json": "TEXT NOT NULL DEFAULT '{}'",
        }
        for name, declaration in job_result_columns.items():
            if name not in result_columns:
                db.execute(f"ALTER TABLE job_results ADD COLUMN {name} {declaration}")
        executor_columns = {row["name"] for row in db.execute("PRAGMA table_info(executors)")}
        executor_additions = {
            "capability_snapshot_json": "TEXT NOT NULL DEFAULT '{}'",
            "gpu_label": "TEXT",
            "office_capability": "TEXT NOT NULL DEFAULT 'none'",
        }
        for name, declaration in executor_additions.items():
            if name not in executor_columns:
                db.execute(f"ALTER TABLE executors ADD COLUMN {name} {declaration}")
        operation_columns = {
            row["name"] for row in db.execute("PRAGMA table_info(operations)")
        }
        if "kind" not in operation_columns:
            db.execute("ALTER TABLE operations ADD COLUMN kind TEXT NOT NULL DEFAULT 'legacy'")
        if "target_keys_json" not in operation_columns:
            db.execute(
                "ALTER TABLE operations ADD COLUMN target_keys_json TEXT NOT NULL DEFAULT '[]'"
            )
        if "conflict_id" not in operation_columns:
            db.execute("ALTER TABLE operations ADD COLUMN conflict_id TEXT")
        db.execute(
            "CREATE TABLE IF NOT EXISTS sync_conflicts ("
            "id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id) "
            "ON DELETE CASCADE, operation_id TEXT NOT NULL UNIQUE, "
            "idempotency_key TEXT NOT NULL UNIQUE, actor_id TEXT NOT NULL, "
            "base_revision_id TEXT NOT NULL, head_revision_id TEXT NOT NULL, "
            "kind TEXT NOT NULL, paths_json TEXT NOT NULL, operation_json TEXT NOT NULL, "
            "status TEXT NOT NULL, resolution_json TEXT, resolved_revision_id TEXT, "
            "created_at TEXT NOT NULL, resolved_at TEXT)"
        )

    def create_organization(self, actor_id: str, name: str) -> dict[str, str]:
        organization_id = str(uuid4())
        created_at = _now()
        created_by = _principal_id(actor_id)
        with self._lock, self._connect() as db:
            db.execute(
                "INSERT INTO organizations "
                "(id, name, owner_actor_id, created_by, created_at) VALUES (?, ?, ?, ?, ?)",
                (organization_id, name, actor_id, created_by, created_at),
            )
        return {
            "organization_id": organization_id,
            "name": name,
            "created_at": created_at,
            "created_by": created_by,
        }

    def list_organizations(self, actor_id: str) -> list[dict[str, str]]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT DISTINCT o.id, o.name, o.created_at, o.created_by "
                "FROM organizations o "
                "LEFT JOIN workspaces w ON w.organization_id=o.id "
                "LEFT JOIN members m ON m.workspace_id=w.id "
                "WHERE o.owner_actor_id=? OR m.actor_id=? "
                "ORDER BY o.created_at, o.id",
                (actor_id, actor_id),
            ).fetchall()
        return [
            {
                "organization_id": row["id"],
                "name": row["name"],
                "created_at": row["created_at"],
                "created_by": row["created_by"],
            }
            for row in rows
        ]

    @staticmethod
    def _organization_access(
        db: sqlite3.Connection, organization_id: str, actor_id: str
    ) -> None:
        row = db.execute(
            "SELECT 1 FROM organizations WHERE id=? AND owner_actor_id=?",
            (organization_id, actor_id),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="organization_not_found")

    def _personal_organization(self, db: sqlite3.Connection, actor_id: str) -> str:
        organization_id = str(
            uuid5(NAMESPACE_URL, f"ppt-video-workbench:personal-organization:{actor_id}")
        )
        db.execute(
            "INSERT INTO organizations "
            "(id, name, owner_actor_id, created_by, created_at) VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(id) DO NOTHING",
            (organization_id, "Personal", actor_id, _principal_id(actor_id), _now()),
        )
        return organization_id

    def create_workspace(
        self,
        actor_id: str,
        name: str,
        organization_id: str | None = None,
    ) -> dict[str, Any]:
        workspace_id = str(uuid4())
        created_at = _now()
        created_by = _principal_id(actor_id)
        with self._lock, self._connect() as db:
            if organization_id is None:
                organization_id = self._personal_organization(db, actor_id)
            else:
                self._organization_access(db, organization_id, actor_id)
            db.execute(
                "INSERT INTO workspaces "
                "(id, name, created_at, organization_id, created_by) VALUES (?, ?, ?, ?, ?)",
                (workspace_id, name, created_at, organization_id, created_by),
            )
            db.execute(
                "INSERT INTO members "
                "(workspace_id, actor_id, role, membership_version, created_at) "
                "VALUES (?, ?, 'owner', 1, ?)",
                (workspace_id, actor_id, created_at),
            )
        return {
            "workspace_id": workspace_id,
            "organization_id": organization_id,
            "name": name,
            "role": "owner",
            "created_at": created_at,
            "created_by": created_by,
        }

    def list_workspaces(self, actor_id: str) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT w.id, w.organization_id, w.name, w.created_at, w.created_by, m.role "
                "FROM workspaces w "
                "JOIN members m ON m.workspace_id=w.id WHERE m.actor_id=? "
                "ORDER BY w.created_at, w.id",
                (actor_id,),
            ).fetchall()
        return [
            {
                "workspace_id": row["id"],
                "organization_id": row["organization_id"],
                "name": row["name"],
                "role": row["role"],
                "created_at": row["created_at"],
                "created_by": row["created_by"],
            }
            for row in rows
        ]

    def memberships(self, actor_id: str) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT workspace_id, role, membership_version, created_at "
                "FROM members WHERE actor_id=? ORDER BY workspace_id",
                (actor_id,),
            ).fetchall()
        user_id = _principal_id(actor_id)
        return [
            {
                "workspace_id": row["workspace_id"],
                "user_id": user_id,
                "role": row["role"],
                "membership_version": row["membership_version"],
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def list_members(self, workspace_id: str, actor_id: str) -> list[dict[str, Any]]:
        with self._connect() as db:
            self._workspace_access(db, workspace_id, actor_id)
            rows = db.execute(
                "SELECT actor_id, role, membership_version, created_at "
                "FROM members WHERE workspace_id=? ORDER BY actor_id",
                (workspace_id,),
            ).fetchall()
        return [
            {
                "workspace_id": workspace_id,
                "user_id": _principal_id(row["actor_id"]),
                "role": row["role"],
                "membership_version": row["membership_version"],
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def add_member(self, workspace_id: str, actor_id: str, member: MemberAdd) -> dict[str, Any]:
        created_at = _now()
        with self._lock, self._connect() as db:
            role = self._workspace_access(db, workspace_id, actor_id)
            if role not in {"owner", "admin"}:
                raise HTTPException(status_code=403, detail="member_admin_required")
            db.execute(
                "INSERT INTO members "
                "(workspace_id, actor_id, role, membership_version, created_at) "
                "VALUES (?, ?, ?, 1, ?) ON CONFLICT(workspace_id, actor_id) "
                "DO UPDATE SET role=excluded.role, "
                "membership_version=members.membership_version + 1",
                (workspace_id, member.actor_id, member.role, created_at),
            )
            record = db.execute(
                "SELECT role, membership_version, created_at FROM members "
                "WHERE workspace_id=? AND actor_id=?",
                (workspace_id, member.actor_id),
            ).fetchone()
        assert record is not None
        return {
            "workspace_id": workspace_id,
            "user_id": _principal_id(member.actor_id),
            "role": record["role"],
            "membership_version": record["membership_version"],
            "created_at": record["created_at"],
        }

    def revoke_member(
        self, workspace_id: str, actor_id: str, target_actor_id: str
    ) -> dict[str, Any]:
        with self._lock, self._connect() as db:
            role = self._workspace_access(db, workspace_id, actor_id)
            if role not in {"owner", "admin"}:
                raise HTTPException(status_code=403, detail="member_admin_required")
            target = db.execute(
                "SELECT role, membership_version FROM members "
                "WHERE workspace_id=? AND actor_id=?",
                (workspace_id, target_actor_id),
            ).fetchone()
            if target is None:
                raise HTTPException(status_code=404, detail="member_not_found")
            if target["role"] == "owner":
                raise HTTPException(status_code=409, detail="workspace_owner_cannot_be_revoked")
            db.execute(
                "DELETE FROM members WHERE workspace_id=? AND actor_id=?",
                (workspace_id, target_actor_id),
            )
        return {
            "workspace_id": workspace_id,
            "user_id": _principal_id(target_actor_id),
            "status": "revoked",
            "membership_version": int(target["membership_version"]) + 1,
        }

    def assert_active_device(self, actor_id: str, device_id: str | None) -> None:
        if device_id is None:
            return
        with self._connect() as db:
            row = db.execute(
                "SELECT status FROM devices WHERE id=? AND actor_id=?",
                (device_id, actor_id),
            ).fetchone()
        if row is None or row["status"] != "active":
            raise HTTPException(status_code=401, detail="device_revoked_or_unknown")

    def register_device(self, actor_id: str, device: DeviceRegister) -> dict[str, str]:
        now = _now()
        with self._lock, self._connect() as db:
            existing = db.execute(
                "SELECT actor_id FROM devices WHERE id=?", (str(device.device_id),)
            ).fetchone()
            if existing is not None and existing["actor_id"] != actor_id:
                raise HTTPException(status_code=409, detail="device_id_conflict")
            db.execute(
                "INSERT INTO devices "
                "(id, actor_id, user_id, name, platform, status, registered_at, last_seen_at) "
                "VALUES (?, ?, ?, ?, ?, 'active', ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET name=excluded.name, platform=excluded.platform, "
                "status='active', last_seen_at=excluded.last_seen_at",
                (
                    str(device.device_id),
                    actor_id,
                    _principal_id(actor_id),
                    device.name,
                    device.platform,
                    now,
                    now,
                ),
            )
            row = db.execute(
                "SELECT * FROM devices WHERE id=?", (str(device.device_id),)
            ).fetchone()
        assert row is not None
        return self._device_dict(row)

    def list_devices(self, actor_id: str) -> list[dict[str, str]]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT * FROM devices WHERE actor_id=? ORDER BY registered_at, id", (actor_id,)
            ).fetchall()
        return [self._device_dict(row) for row in rows]

    def revoke_device(self, actor_id: str, device_id: str) -> dict[str, str]:
        with self._lock, self._connect() as db:
            row = db.execute(
                "SELECT * FROM devices WHERE id=? AND actor_id=?", (device_id, actor_id)
            ).fetchone()
            if row is None:
                raise HTTPException(status_code=404, detail="device_not_found")
            db.execute("UPDATE devices SET status='revoked' WHERE id=?", (device_id,))
            row = db.execute("SELECT * FROM devices WHERE id=?", (device_id,)).fetchone()
        assert row is not None
        return self._device_dict(row)

    @staticmethod
    def _device_dict(row: sqlite3.Row) -> dict[str, str]:
        return {
            "device_id": row["id"],
            "user_id": row["user_id"],
            "name": row["name"],
            "platform": row["platform"],
            "status": row["status"],
            "registered_at": row["registered_at"],
            "last_seen_at": row["last_seen_at"],
        }

    def create_service_account(
        self, workspace_id: str, actor_id: str, account: ServiceAccountCreate
    ) -> dict[str, str]:
        account_id = str(uuid4())
        created_at = _now()
        created_by = _principal_id(actor_id)
        with self._lock, self._connect() as db:
            role = self._workspace_access(db, workspace_id, actor_id)
            if role not in {"owner", "admin"}:
                raise HTTPException(status_code=403, detail="service_account_admin_required")
            try:
                db.execute(
                    "INSERT INTO service_accounts "
                    "(id, workspace_id, name, status, created_at, created_by) "
                    "VALUES (?, ?, ?, 'active', ?, ?)",
                    (account_id, workspace_id, account.name, created_at, created_by),
                )
            except sqlite3.IntegrityError as error:
                raise HTTPException(
                    status_code=409, detail="service_account_name_conflict"
                ) from error
        return {
            "service_account_id": account_id,
            "workspace_id": workspace_id,
            "name": account.name,
            "status": "active",
            "created_at": created_at,
            "created_by": created_by,
        }

    def list_service_accounts(
        self, workspace_id: str, actor_id: str
    ) -> list[dict[str, str]]:
        with self._connect() as db:
            role = self._workspace_access(db, workspace_id, actor_id)
            if role not in {"owner", "admin"}:
                raise HTTPException(status_code=403, detail="service_account_admin_required")
            rows = db.execute(
                "SELECT * FROM service_accounts WHERE workspace_id=? ORDER BY created_at, id",
                (workspace_id,),
            ).fetchall()
        return [self._service_account_dict(row) for row in rows]

    def disable_service_account(
        self, workspace_id: str, actor_id: str, account_id: str
    ) -> dict[str, str]:
        with self._lock, self._connect() as db:
            role = self._workspace_access(db, workspace_id, actor_id)
            if role not in {"owner", "admin"}:
                raise HTTPException(status_code=403, detail="service_account_admin_required")
            row = db.execute(
                "SELECT * FROM service_accounts WHERE id=? AND workspace_id=?",
                (account_id, workspace_id),
            ).fetchone()
            if row is None:
                raise HTTPException(status_code=404, detail="service_account_not_found")
            db.execute("UPDATE service_accounts SET status='disabled' WHERE id=?", (account_id,))
            row = db.execute("SELECT * FROM service_accounts WHERE id=?", (account_id,)).fetchone()
        assert row is not None
        return self._service_account_dict(row)

    @staticmethod
    def _service_account_dict(row: sqlite3.Row) -> dict[str, str]:
        return {
            "service_account_id": row["id"],
            "workspace_id": row["workspace_id"],
            "name": row["name"],
            "status": row["status"],
            "created_at": row["created_at"],
            "created_by": row["created_by"],
        }

    def _workspace_access(self, db: sqlite3.Connection, workspace_id: str, actor_id: str) -> str:
        row = db.execute(
            "SELECT m.role FROM members m WHERE m.workspace_id=? AND m.actor_id=?",
            (workspace_id, actor_id),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="workspace_not_found")
        return str(row["role"])

    def create_project(
        self, workspace_id: str, actor_id: str, name: str, manifest: dict[str, Any]
    ) -> dict[str, Any]:
        _assert_portable_document(manifest, field="manifest")
        project_id, revision_id = str(uuid4()), str(uuid4())
        created_at = _now()
        manifest_json = json.dumps(
            manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        content_hash = canonical_sha256(manifest)
        with self._lock, self._connect() as db:
            self._workspace_access(db, workspace_id, actor_id)
            db.execute(
                "INSERT INTO projects VALUES (?, ?, ?, ?, ?)",
                (project_id, workspace_id, name, revision_id, created_at),
            )
            db.execute(
                "INSERT INTO revisions VALUES (?, ?, 1, NULL, ?, ?, ?)",
                (revision_id, project_id, content_hash, manifest_json, created_at),
            )
        return self.project(workspace_id, project_id, actor_id)

    def project(self, workspace_id: str, project_id: str, actor_id: str) -> dict[str, Any]:
        with self._connect() as db:
            self._workspace_access(db, workspace_id, actor_id)
            row = db.execute(
                "SELECT p.* FROM projects p WHERE p.id=? AND p.workspace_id=?",
                (project_id, workspace_id),
            ).fetchone()
            if row is None:
                raise HTTPException(status_code=404, detail="project_not_found")
            revision = db.execute(
                "SELECT * FROM revisions WHERE id=?", (row["current_revision_id"],)
            ).fetchone()
        if revision is None:
            raise HTTPException(status_code=500, detail="project_head_missing")
        return {
            "project_id": row["id"],
            "workspace_id": row["workspace_id"],
            "name": row["name"],
            "current_revision_id": row["current_revision_id"],
            "created_at": row["created_at"],
            "head": self._revision_dict(revision),
        }

    def list_projects(self, workspace_id: str, actor_id: str) -> list[dict[str, Any]]:
        with self._connect() as db:
            self._workspace_access(db, workspace_id, actor_id)
            rows = db.execute(
                "SELECT id, name, current_revision_id, created_at FROM projects "
                "WHERE workspace_id=? ORDER BY created_at, id",
                (workspace_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def _revision_dict(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "revision_id": row["id"],
            "project_id": row["project_id"],
            "sequence": row["sequence"],
            "parent_revision_id": row["parent_id"],
            "content_sha256": row["content_hash"],
            "manifest": json.loads(row["manifest_json"]),
            "created_at": row["created_at"],
        }

    def revisions(self, workspace_id: str, project_id: str, actor_id: str) -> list[dict[str, Any]]:
        self.project(workspace_id, project_id, actor_id)
        with self._connect() as db:
            rows = db.execute(
                "SELECT r.* FROM revisions r WHERE r.project_id=? ORDER BY r.sequence DESC",
                (project_id,),
            ).fetchall()
        return [self._revision_dict(row) for row in rows]

    def revision(
        self, workspace_id: str, project_id: str, revision_id: str, actor_id: str
    ) -> dict[str, Any]:
        self.project(workspace_id, project_id, actor_id)
        with self._connect() as db:
            row = db.execute(
                "SELECT * FROM revisions WHERE id=? AND project_id=?",
                (revision_id, project_id),
            ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="revision_not_found")
        return self._revision_dict(row)

    def append_operation(
        self, workspace_id: str, project_id: str, actor_id: str, operation: SyncOperation
    ) -> dict[str, Any]:
        if str(operation.workspace_id) != workspace_id or str(operation.project_id) != project_id:
            raise HTTPException(status_code=422, detail="operation_scope_mismatch")
        if canonical_sha256(operation.payload) != operation.payload_sha256:
            raise HTTPException(status_code=422, detail="payload_hash_mismatch")
        _assert_portable_document(operation.payload, field="operation.payload")
        target_keys = _sync_target_keys(operation.kind, operation.payload)
        with self._lock, self._connect() as db:
            self._workspace_access(db, workspace_id, actor_id)
            project = db.execute(
                "SELECT * FROM projects WHERE id=? AND workspace_id=?", (project_id, workspace_id)
            ).fetchone()
            if project is None:
                raise HTTPException(status_code=404, detail="project_not_found")
            existing = db.execute(
                "SELECT * FROM operations WHERE idempotency_key=?",
                (str(operation.idempotency_key),),
            ).fetchone()
            if existing is not None:
                stored = json.loads(existing["payload_json"])
                if (
                    existing["id"] != str(operation.operation_id)
                    or stored.get("payload_sha256") != operation.payload_sha256
                ):
                    raise HTTPException(status_code=409, detail="operation_idempotency_conflict")
                revision = db.execute(
                    "SELECT * FROM revisions WHERE id=?", (existing["revision_id"],)
                ).fetchone()
                return {
                    "operation_id": existing["id"],
                    "accepted_attempt_id": str(operation.attempt_id),
                    "revision": self._revision_dict(revision),
                    "cursor": existing["id"],
                    "conflict": None,
                }
            existing_conflict = db.execute(
                "SELECT * FROM sync_conflicts WHERE idempotency_key=?",
                (str(operation.idempotency_key),),
            ).fetchone()
            if existing_conflict is not None:
                raise HTTPException(
                    status_code=409, detail=self._sync_conflict_dict(existing_conflict)
                )
            base = db.execute(
                "SELECT * FROM revisions WHERE id=? AND project_id=?",
                (str(operation.base_revision_id), project_id),
            ).fetchone()
            if base is None:
                raise HTTPException(status_code=409, detail="sync_base_revision_missing")
            if str(operation.base_revision_id) != project["current_revision_id"]:
                rows = db.execute(
                    "SELECT o.kind, o.target_keys_json FROM operations o "
                    "JOIN revisions r ON r.id=o.revision_id "
                    "WHERE o.project_id=? AND r.sequence>? ORDER BY r.sequence",
                    (project_id, int(base["sequence"])),
                ).fetchall()
                intervening: list[tuple[str, set[str]]] = []
                overlapping_paths: set[str] = set()
                incoming = set(target_keys)
                for row in rows:
                    paths = set(json.loads(row["target_keys_json"]))
                    if not paths:
                        paths = {"*"}
                    intervening.append((str(row["kind"]), paths))
                    if "*" in paths:
                        overlapping_paths.update(incoming)
                    else:
                        overlapping_paths.update(incoming & paths)
                if overlapping_paths:
                    conflict_id = str(uuid4())
                    conflict_kind = _sync_conflict_kind(
                        operation.kind, incoming, intervening
                    )
                    created_at = _now()
                    db.execute(
                        "INSERT INTO sync_conflicts "
                        "(id, project_id, operation_id, idempotency_key, actor_id, "
                        "base_revision_id, head_revision_id, kind, paths_json, "
                        "operation_json, status, created_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'open', ?)",
                        (
                            conflict_id,
                            project_id,
                            str(operation.operation_id),
                            str(operation.idempotency_key),
                            actor_id,
                            str(operation.base_revision_id),
                            project["current_revision_id"],
                            conflict_kind,
                            json.dumps(sorted(overlapping_paths)),
                            json.dumps(operation.model_dump(mode="json"), sort_keys=True),
                            created_at,
                        ),
                    )
                    conflict = db.execute(
                        "SELECT * FROM sync_conflicts WHERE id=?", (conflict_id,)
                    ).fetchone()
                    assert conflict is not None
                    db.commit()
                    raise HTTPException(
                        status_code=409, detail=self._sync_conflict_dict(conflict)
                    )
            parent = db.execute(
                "SELECT * FROM revisions WHERE id=?", (project["current_revision_id"],)
            ).fetchone()
            if parent is None:
                raise HTTPException(status_code=500, detail="project_head_missing")
            revision = self._commit_sync_operation(
                db, project_id, actor_id, operation, parent, target_keys
            )
            operation_id = str(operation.operation_id)
        return {
            "operation_id": operation_id,
            "accepted_attempt_id": str(operation.attempt_id),
            "revision": self._revision_dict(revision),
            "cursor": operation_id,
            "conflict": None,
        }

    @staticmethod
    def _commit_sync_operation(
        db: sqlite3.Connection,
        project_id: str,
        actor_id: str,
        operation: SyncOperation,
        parent: sqlite3.Row,
        target_keys: list[str],
        *,
        conflict_id: str | None = None,
    ) -> sqlite3.Row:
        manifest = _apply_sync_operation(
            json.loads(parent["manifest_json"]), operation.kind, operation.payload, target_keys
        )
        revision_id = str(uuid4())
        operation_id = str(operation.operation_id)
        created_at = _now()
        db.execute(
            "INSERT INTO revisions VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                revision_id,
                project_id,
                int(parent["sequence"]) + 1,
                parent["id"],
                canonical_sha256(manifest),
                json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                created_at,
            ),
        )
        db.execute(
            "UPDATE projects SET current_revision_id=? WHERE id=?",
            (revision_id, project_id),
        )
        db.execute(
            "INSERT INTO operations "
            "(id, idempotency_key, project_id, actor_id, base_revision_id, revision_id, "
            "payload_json, created_at, kind, target_keys_json, conflict_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                operation_id,
                str(operation.idempotency_key),
                project_id,
                actor_id,
                str(operation.base_revision_id),
                revision_id,
                json.dumps(operation.model_dump(mode="json"), separators=(",", ":")),
                created_at,
                operation.kind,
                json.dumps(target_keys),
                conflict_id,
            ),
        )
        revision = cast(
            sqlite3.Row,
            db.execute("SELECT * FROM revisions WHERE id=?", (revision_id,)).fetchone(),
        )
        assert revision is not None
        return revision

    @staticmethod
    def _sync_conflict_dict(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "conflict_id": row["id"],
            "project_id": row["project_id"],
            "operation_id": row["operation_id"],
            "base_revision_id": row["base_revision_id"],
            "head_revision_id": row["head_revision_id"],
            "kind": row["kind"],
            "paths": json.loads(row["paths_json"]),
            "status": row["status"],
            "resolution": (
                json.loads(row["resolution_json"]) if row["resolution_json"] else None
            ),
            "resolved_revision_id": row["resolved_revision_id"],
            "created_at": row["created_at"],
            "resolved_at": row["resolved_at"],
        }

    def sync_conflicts(
        self, workspace_id: str, project_id: str, actor_id: str
    ) -> list[dict[str, Any]]:
        self.project(workspace_id, project_id, actor_id)
        with self._connect() as db:
            rows = db.execute(
                "SELECT * FROM sync_conflicts WHERE project_id=? ORDER BY created_at, id",
                (project_id,),
            ).fetchall()
        return [self._sync_conflict_dict(row) for row in rows]

    def resolve_sync_conflict(
        self,
        workspace_id: str,
        project_id: str,
        conflict_id: str,
        actor_id: str,
        resolution: SyncConflictResolution,
    ) -> dict[str, Any]:
        self.project(workspace_id, project_id, actor_id)
        _assert_portable_document(
            resolution.merged_payload or {}, field="conflict.merged_payload"
        )
        with self._lock, self._connect() as db:
            conflict = db.execute(
                "SELECT * FROM sync_conflicts WHERE id=? AND project_id=?",
                (conflict_id, project_id),
            ).fetchone()
            if conflict is None:
                raise HTTPException(status_code=404, detail="sync_conflict_not_found")
            if conflict["status"] == "resolved":
                return self._sync_conflict_dict(conflict)
            project = db.execute(
                "SELECT * FROM projects WHERE id=? AND workspace_id=?", (project_id, workspace_id)
            ).fetchone()
            if project is None:
                raise HTTPException(status_code=404, detail="project_not_found")
            if str(resolution.expected_head_revision_id) != project["current_revision_id"]:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": "revision_conflict",
                        "head_revision_id": project["current_revision_id"],
                    },
                )
            resolved_revision_id: str | None = None
            if resolution.strategy != "keep_remote":
                operation = SyncOperation.model_validate(json.loads(conflict["operation_json"]))
                payload = (
                    resolution.merged_payload
                    if resolution.strategy == "merged"
                    else operation.payload
                )
                assert payload is not None
                operation = operation.model_copy(
                    update={
                        "base_revision_id": UUID(project["current_revision_id"]),
                        "payload": payload,
                        "payload_sha256": canonical_sha256(payload),
                    }
                )
                target_keys = _sync_target_keys(operation.kind, operation.payload)
                parent = db.execute(
                    "SELECT * FROM revisions WHERE id=?", (project["current_revision_id"],)
                ).fetchone()
                if parent is None:
                    raise HTTPException(status_code=500, detail="project_head_missing")
                revision = self._commit_sync_operation(
                    db,
                    project_id,
                    actor_id,
                    operation,
                    parent,
                    target_keys,
                    conflict_id=conflict_id,
                )
                resolved_revision_id = str(revision["id"])
            resolved_at = _now()
            db.execute(
                "UPDATE sync_conflicts SET status='resolved', resolution_json=?, "
                "resolved_revision_id=?, resolved_at=? WHERE id=?",
                (
                    json.dumps(resolution.model_dump(mode="json"), sort_keys=True),
                    resolved_revision_id,
                    resolved_at,
                    conflict_id,
                ),
            )
            updated = db.execute(
                "SELECT * FROM sync_conflicts WHERE id=?", (conflict_id,)
            ).fetchone()
        assert updated is not None
        return self._sync_conflict_dict(updated)

    def operations(
        self, workspace_id: str, project_id: str, actor_id: str, cursor: str | None
    ) -> list[dict[str, Any]]:
        self.project(workspace_id, project_id, actor_id)
        with self._connect() as db:
            rows = db.execute(
                "SELECT * FROM operations WHERE project_id=? ORDER BY rowid", (project_id,)
            ).fetchall()
        if cursor:
            rows = rows[
                next(
                    (index + 1 for index, row in enumerate(rows) if row["id"] == cursor), len(rows)
                ) :
            ]
        return [
            json.loads(row["payload_json"]) | {"server_revision_id": row["revision_id"]}
            for row in rows
        ]

    def initiate_upload(
        self, workspace_id: str, project_id: str, actor_id: str, declaration: dict[str, Any]
    ) -> dict[str, Any]:
        self.project(workspace_id, project_id, actor_id)
        object_id = str(declaration.get("object_id", ""))
        size = int(declaration.get("size_bytes", -1))
        media_type = str(declaration.get("media_type", "application/octet-stream"))
        classification = str(declaration.get("classification", "internal"))
        if (
            not re.fullmatch(r"sha256:[0-9a-f]{64}", object_id)
            or size < 0
            or size > 10 * 1024 * 1024 * 1024
            or not re.fullmatch(r"[\w.+-]+/[\w.+-]+", media_type)
            or classification not in {"public", "internal", "sensitive", "restricted"}
            or classification == "restricted"
        ):
            raise HTTPException(status_code=422, detail="invalid_or_restricted_object")
        upload_id, expires_at = str(uuid4()), _expires(900)
        with self._connect() as db:
            db.execute(
                "INSERT INTO uploads VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)",
                (upload_id, project_id, object_id, size, media_type, classification, expires_at),
            )
        return {
            "upload_id": upload_id,
            "object_id": object_id,
            "parts": [
                {
                    "part_number": 1,
                    "method": "PUT",
                    "url": f"https://object.invalid/upload/{upload_id}/1",
                    "local_endpoint": (
                        f"/v1/workspaces/{workspace_id}/projects/{project_id}/"
                        f"objects/uploads/{upload_id}/parts/1"
                    ),
                    "expires_at": expires_at,
                }
            ],
            "expires_at": expires_at,
        }

    def upload_part(
        self,
        workspace_id: str,
        project_id: str,
        actor_id: str,
        upload_id: str,
        part_number: int,
        content: bytes,
    ) -> dict[str, Any]:
        """Store one upload part in a private staging area."""

        self.project(workspace_id, project_id, actor_id)
        if part_number < 1 or part_number > 10_000:
            raise HTTPException(status_code=422, detail="invalid_part_number")
        if len(content) > 64 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="upload_part_too_large")
        with self._connect() as db:
            upload = db.execute(
                "SELECT * FROM uploads WHERE id=? AND project_id=?", (upload_id, project_id)
            ).fetchone()
        if upload is None or upload["status"] != "pending":
            raise HTTPException(status_code=404, detail="upload_not_found")
        if datetime.fromisoformat(upload["expires_at"].replace("Z", "+00:00")) <= datetime.now(
            UTC
        ):
            raise HTTPException(status_code=409, detail="upload_expired")
        if not re.fullmatch(r"[0-9a-f-]{36}", upload_id):
            raise HTTPException(status_code=422, detail="invalid_upload_id")
        root = self.object_root.resolve()
        upload_root = (root / ".uploads" / upload_id).resolve()
        upload_root.mkdir(parents=True, exist_ok=True)
        target = (upload_root / f"{part_number:08d}.part").resolve()
        try:
            target.relative_to(root)
        except ValueError as error:
            raise HTTPException(status_code=422, detail="invalid_upload_path") from error
        handle, temporary_name = tempfile.mkstemp(prefix=".part-", dir=upload_root)
        try:
            with os.fdopen(handle, "wb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary_name, target)
        except BaseException:
            with suppress(FileNotFoundError):
                os.unlink(temporary_name)
            raise
        digest = "sha256:" + hashlib.sha256(content).hexdigest()
        return {
            "upload_id": upload_id,
            "part_number": part_number,
            "size_bytes": len(content),
            "etag": digest,
        }

    def complete_upload(
        self,
        workspace_id: str,
        project_id: str,
        actor_id: str,
        upload_id: str,
        parts: list[dict[str, Any]],
    ) -> dict[str, Any]:
        self.project(workspace_id, project_id, actor_id)
        with self._lock, self._connect() as db:
            upload = db.execute(
                "SELECT * FROM uploads WHERE id=? AND project_id=?", (upload_id, project_id)
            ).fetchone()
            if upload is None or upload["status"] != "pending":
                raise HTTPException(status_code=404, detail="upload_not_found")
            if datetime.fromisoformat(upload["expires_at"].replace("Z", "+00:00")) <= datetime.now(
                UTC
            ):
                raise HTTPException(status_code=409, detail="upload_expired")
            if not parts:
                raise HTTPException(status_code=422, detail="parts_required")
            part_numbers: set[int] = set()
            declared_sizes: list[int] = []
            for part in parts:
                try:
                    part_number = int(part.get("part_number", 0))
                    etag = str(part.get("etag", ""))
                except (AttributeError, TypeError, ValueError) as error:
                    raise HTTPException(status_code=422, detail="invalid_upload_part") from error
                if part_number < 1 or part_number in part_numbers or not etag:
                    raise HTTPException(status_code=422, detail="invalid_upload_part")
                part_numbers.add(part_number)
                if "size_bytes" in part:
                    try:
                        part_size = int(part["size_bytes"])
                    except (TypeError, ValueError) as error:
                        raise HTTPException(
                            status_code=422, detail="invalid_upload_part"
                        ) from error
                    if part_size < 0:
                        raise HTTPException(status_code=422, detail="invalid_upload_part")
                    declared_sizes.append(part_size)
            if declared_sizes and sum(declared_sizes) != upload["size_bytes"]:
                raise HTTPException(status_code=422, detail="upload_size_mismatch")
            if not re.fullmatch(r"[0-9a-f-]{36}", upload_id):
                raise HTTPException(status_code=422, detail="invalid_upload_id")
            root = self.object_root.resolve()
            upload_root = (root / ".uploads" / upload_id).resolve()
            try:
                upload_root.relative_to(root)
            except ValueError as error:
                raise HTTPException(status_code=422, detail="invalid_upload_path") from error
            part_paths: list[Path] = []
            for part in sorted(parts, key=lambda item: int(item.get("part_number", 0))):
                part_number = int(part.get("part_number", 0))
                candidate = (upload_root / f"{part_number:08d}.part").resolve()
                try:
                    candidate.relative_to(upload_root)
                except ValueError as error:
                    raise HTTPException(status_code=422, detail="invalid_upload_path") from error
                if candidate.exists():
                    content = candidate.read_bytes()
                    expected_etag = "sha256:" + hashlib.sha256(content).hexdigest()
                    if str(part.get("etag", "")) != expected_etag:
                        raise HTTPException(status_code=422, detail="upload_part_hash_mismatch")
                    part_paths.append(candidate)
                elif upload["size_bytes"] > 0:
                    raise HTTPException(status_code=422, detail="upload_content_missing")
            content = b"".join(path.read_bytes() for path in part_paths)
            if len(content) != upload["size_bytes"]:
                raise HTTPException(status_code=422, detail="upload_size_mismatch")
            content_digest = "sha256:" + hashlib.sha256(content).hexdigest()
            if content_digest != upload["object_id"]:
                raise HTTPException(status_code=422, detail="upload_hash_mismatch")
            _validate_uploaded_content(upload["media_type"], content)
            object_path = self._object_path(project_id, upload["object_id"])
            storage_key = f"{project_id}/{upload['object_id'].removeprefix('sha256:')}"
            object_path.parent.mkdir(parents=True, exist_ok=True)
            if not object_path.exists():
                handle, temporary_name = tempfile.mkstemp(
                    prefix=".object-", dir=object_path.parent
                )
                try:
                    with os.fdopen(handle, "wb") as stream:
                        stream.write(content)
                        stream.flush()
                        os.fsync(stream.fileno())
                    os.replace(temporary_name, object_path)
                except BaseException:
                    with suppress(FileNotFoundError):
                        os.unlink(temporary_name)
                    raise
            db.execute("UPDATE uploads SET status='complete' WHERE id=?", (upload_id,))
            db.execute(
                "INSERT OR IGNORE INTO objects VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    upload["object_id"],
                    project_id,
                    upload["size_bytes"],
                    upload["media_type"],
                    upload["classification"],
                    storage_key,
                    _now(),
                ),
            )
            row = db.execute(
                "SELECT * FROM objects WHERE id=? AND project_id=?",
                (upload["object_id"], project_id),
            ).fetchone()
        return {
            "object_id": row["id"],
            "project_id": project_id,
            "size_bytes": row["size_bytes"],
            "media_type": row["media_type"],
            "classification": row["classification"],
            "storage_key": f"{project_id}/{row['id']}",
        }

    def read_object(
        self, workspace_id: str, project_id: str, actor_id: str, object_id: str
    ) -> tuple[bytes, str]:
        self.project(workspace_id, project_id, actor_id)
        with self._connect() as db:
            row = db.execute(
                "SELECT * FROM objects WHERE id=? AND project_id=?", (object_id, project_id)
            ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="object_not_found")
        path = self._object_path(project_id, object_id)
        try:
            content = path.read_bytes()
        except OSError as error:
            raise HTTPException(status_code=404, detail="object_content_not_found") from error
        digest = "sha256:" + hashlib.sha256(content).hexdigest()
        if len(content) != row["size_bytes"] or digest != object_id:
            raise HTTPException(status_code=500, detail="object_integrity_failed")
        return content, str(row["media_type"])

    def authorize_download(
        self, workspace_id: str, project_id: str, actor_id: str, object_id: str
    ) -> dict[str, Any]:
        self.project(workspace_id, project_id, actor_id)
        with self._connect() as db:
            row = db.execute(
                "SELECT * FROM objects WHERE id=? AND project_id=?", (object_id, project_id)
            ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="object_not_found")
        return {
            "method": "GET",
            "url": f"https://object.invalid/download/{project_id}/{object_id}",
            "object_id": object_id,
            "size_bytes": row["size_bytes"],
            "expires_at": _expires(300),
        }

    def comment(
        self,
        workspace_id: str,
        project_id: str,
        actor_id: str,
        body: str,
        anchor: CommentAnchorModel,
    ) -> dict[str, Any]:
        self.project(workspace_id, project_id, actor_id)
        anchor_data = anchor.model_dump(mode="json", exclude_none=True)
        comment_id, created_at = str(uuid4()), _now()
        with self._connect() as db:
            revision = db.execute(
                "SELECT 1 FROM revisions WHERE id=? AND project_id=?",
                (str(anchor.revision_id), project_id),
            ).fetchone()
            if revision is None:
                raise HTTPException(status_code=422, detail="comment_revision_not_found")
            if anchor.evidence_object_id is not None:
                evidence = db.execute(
                    "SELECT 1 FROM objects WHERE id=? AND project_id=?",
                    (anchor.evidence_object_id, project_id),
                ).fetchone()
                if evidence is None:
                    raise HTTPException(status_code=422, detail="comment_evidence_not_owned")
            db.execute(
                "INSERT INTO comments VALUES (?, ?, ?, ?, ?, ?, 0)",
                (
                    comment_id,
                    project_id,
                    actor_id,
                    body,
                    json.dumps(anchor_data, separators=(",", ":")),
                    created_at,
                ),
            )
        return {
            "comment_id": comment_id,
            "project_id": project_id,
            "author_id": _principal_id(actor_id),
            "body": body,
            "anchor": anchor_data,
            "created_at": created_at,
            "resolved": False,
        }

    def comments(self, workspace_id: str, project_id: str, actor_id: str) -> list[dict[str, Any]]:
        self.project(workspace_id, project_id, actor_id)
        with self._connect() as db:
            rows = db.execute(
                "SELECT * FROM comments WHERE project_id=? ORDER BY created_at, id", (project_id,)
            ).fetchall()
        return [
            {
                "comment_id": row["id"],
                "project_id": project_id,
                "author_id": _principal_id(row["actor_id"]),
                "body": row["body"],
                "anchor": json.loads(row["anchor_json"]),
                "created_at": row["created_at"],
                "resolved": bool(row["resolved"]),
            }
            for row in rows
        ]

    def review(
        self, workspace_id: str, project_id: str, actor_id: str, request: ReviewCreate
    ) -> dict[str, Any]:
        project = self.project(workspace_id, project_id, actor_id)
        if str(request.revision_id) != project["current_revision_id"]:
            raise HTTPException(status_code=409, detail="review_revision_is_not_head")
        if request.content_sha256 != project["head"]["content_sha256"]:
            raise HTTPException(status_code=409, detail="review_content_is_not_head")
        review_id, created_at = str(uuid4()), _now()
        with self._connect() as db:
            db.execute(
                "INSERT INTO reviews "
                "(id, project_id, revision_id, actor_id, decision, note, created_at, "
                "content_sha256) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    review_id,
                    project_id,
                    str(request.revision_id),
                    actor_id,
                    request.decision,
                    request.note,
                    created_at,
                    request.content_sha256,
                ),
            )
        return {
            "review_id": review_id,
            "project_id": project_id,
            "revision_id": str(request.revision_id),
            "content_sha256": request.content_sha256,
            "reviewer_id": _principal_id(actor_id),
            "decision": request.decision,
            "note": request.note,
            "created_at": created_at,
            "status": "current",
        }

    def reviews(self, workspace_id: str, project_id: str, actor_id: str) -> list[dict[str, Any]]:
        project = self.project(workspace_id, project_id, actor_id)
        with self._connect() as db:
            rows = db.execute(
                "SELECT * FROM reviews WHERE project_id=? ORDER BY created_at, id",
                (project_id,),
            ).fetchall()
        return [
            {
                "review_id": row["id"],
                "project_id": project_id,
                "revision_id": row["revision_id"],
                "content_sha256": row["content_sha256"],
                "reviewer_id": _principal_id(row["actor_id"]),
                "decision": row["decision"],
                "note": row["note"],
                "created_at": row["created_at"],
                "status": (
                    "current"
                    if row["revision_id"] == project["current_revision_id"]
                    and row["content_sha256"] == project["head"]["content_sha256"]
                    else "expired"
                ),
            }
            for row in rows
        ]

    def lease(
        self, workspace_id: str, project_id: str, actor_id: str, request: LeaseRequest
    ) -> dict[str, Any]:
        project = self.project(workspace_id, project_id, actor_id)
        if str(request.base_revision_id) != project["current_revision_id"]:
            raise HTTPException(status_code=409, detail="lease_base_revision_is_not_head")
        acquired_at = _now()
        with self._lock, self._connect() as db:
            current = db.execute(
                "SELECT * FROM leases WHERE project_id=?", (project_id,)
            ).fetchone()
            if (
                current is not None
                and current["actor_id"] != actor_id
                and datetime.fromisoformat(current["expires_at"].replace("Z", "+00:00"))
                > datetime.now(UTC)
            ):
                raise HTTPException(status_code=409, detail="lease_held_by_another_actor")
            lease_id = str(request.lease_id or uuid4())
            expires_at = _expires(request.requested_ttl_seconds)
            db.execute(
                "INSERT OR REPLACE INTO leases "
                "(project_id, lease_id, actor_id, client_id, expires_at, scope, "
                "base_revision_id, acquired_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    project_id,
                    lease_id,
                    actor_id,
                    str(request.client_id),
                    expires_at,
                    request.scope,
                    str(request.base_revision_id),
                    acquired_at,
                ),
            )
        return {
            "lease_id": lease_id,
            "project_id": project_id,
            "holder_user_id": _principal_id(actor_id),
            "client_id": str(request.client_id),
            "scope": request.scope,
            "base_revision_id": str(request.base_revision_id),
            "acquired_at": acquired_at,
            "expires_at": expires_at,
        }

    def release_lease(
        self,
        workspace_id: str,
        project_id: str,
        actor_id: str,
        reason: str | None,
    ) -> dict[str, Any]:
        self.project(workspace_id, project_id, actor_id)
        with self._lock, self._connect() as db:
            role = self._workspace_access(db, workspace_id, actor_id)
            current = db.execute(
                "SELECT * FROM leases WHERE project_id=?", (project_id,)
            ).fetchone()
            if current is None:
                raise HTTPException(status_code=404, detail="lease_not_found")
            force_release = current["actor_id"] != actor_id
            if force_release and role not in {"owner", "admin"}:
                raise HTTPException(status_code=403, detail="lease_override_admin_required")
            if force_release and not reason:
                raise HTTPException(status_code=422, detail="lease_override_reason_required")
            event_id = str(uuid4())
            action = "force_released" if force_release else "released"
            occurred_at = _now()
            db.execute(
                "INSERT INTO lease_audit_events "
                "(id, project_id, lease_id, actor_id, action, reason, occurred_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    event_id,
                    project_id,
                    current["lease_id"],
                    actor_id,
                    action,
                    reason,
                    occurred_at,
                ),
            )
            db.execute("DELETE FROM leases WHERE project_id=?", (project_id,))
        return {
            "lease_id": current["lease_id"],
            "project_id": project_id,
            "released_by": _principal_id(actor_id),
            "action": action,
            "reason": reason,
            "audit_event_id": event_id,
            "occurred_at": occurred_at,
        }

    def register_executor(
        self, workspace_id: str, actor_id: str, request: ExecutorRegister
    ) -> dict[str, Any]:
        _assert_portable_document(request.capability_snapshot, field="executor.capability_snapshot")
        with self._lock, self._connect() as db:
            self._workspace_access(db, workspace_id, actor_id)
            expires_at = _expires(request.ttl_seconds)
            existing = db.execute(
                "SELECT workspace_id, actor_id FROM executors WHERE id=?",
                (str(request.executor_id),),
            ).fetchone()
            if existing is not None and (
                existing["workspace_id"] != workspace_id or existing["actor_id"] != actor_id
            ):
                raise HTTPException(status_code=403, detail="executor_scope_mismatch")
            db.execute(
                "INSERT INTO executors "
                "(id, workspace_id, actor_id, platform, capabilities_json, region, status, "
                "expires_at, capability_snapshot_json, gpu_label, office_capability) "
                "VALUES (?, ?, ?, ?, ?, ?, 'active', ?, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET platform=excluded.platform, "
                "capabilities_json=excluded.capabilities_json, region=excluded.region, "
                "status='active', expires_at=excluded.expires_at, "
                "capability_snapshot_json=excluded.capability_snapshot_json, "
                "gpu_label=excluded.gpu_label, office_capability=excluded.office_capability",
                (
                    str(request.executor_id),
                    workspace_id,
                    actor_id,
                    request.platform,
                    json.dumps(request.capabilities),
                    request.region,
                    expires_at,
                    json.dumps(request.capability_snapshot, ensure_ascii=False, sort_keys=True),
                    request.gpu_label,
                    request.office_capability,
                ),
            )
        return {
            "executor_id": str(request.executor_id),
            "workspace_id": workspace_id,
            "platform": request.platform,
            "capabilities": request.capabilities,
            "region": request.region,
            "gpu_label": request.gpu_label,
            "office_capability": request.office_capability,
            "status": "active",
            "expires_at": expires_at,
            "capability_snapshot": request.capability_snapshot,
        }

    def executors(self, workspace_id: str, actor_id: str) -> list[dict[str, Any]]:
        with self._connect() as db:
            self._workspace_access(db, workspace_id, actor_id)
            rows = db.execute(
                "SELECT * FROM executors WHERE workspace_id=? ORDER BY id", (workspace_id,)
            ).fetchall()
        now = datetime.now(UTC)
        return [
            {
                "executor_id": row["id"],
                "workspace_id": workspace_id,
                "platform": row["platform"],
                "capabilities": json.loads(row["capabilities_json"]),
                "region": row["region"],
                "gpu_label": row["gpu_label"],
                "office_capability": row["office_capability"],
                "status": (
                    row["status"]
                    if _timestamp(row["expires_at"]) > now
                    else "expired"
                ),
                "expires_at": row["expires_at"],
                "capability_snapshot": json.loads(row["capability_snapshot_json"]),
            }
            for row in rows
        ]

    @staticmethod
    def _select_executor(
        db: sqlite3.Connection,
        workspace_id: str,
        kind: str,
        required_capabilities: set[str] | None = None,
        required_region: str | None = None,
    ) -> sqlite3.Row | None:
        rows = cast(
            list[sqlite3.Row],
            db.execute(
                "SELECT * FROM executors "
                "WHERE workspace_id=? AND status='active' ORDER BY id",
                (workspace_id,),
            ).fetchall(),
        )
        now = datetime.now(UTC)
        for row in rows:
            if _timestamp(row["expires_at"]) <= now:
                continue
            if required_region is not None and row["region"] != required_region:
                continue
            capabilities = set(json.loads(row["capabilities_json"]))
            required = required_capabilities or set()
            if (kind in capabilities or "*" in capabilities) and required.issubset(capabilities):
                return row
        return None

    @staticmethod
    def _job_payload(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "job_id": row["id"],
            "project_id": row["project_id"],
            "revision_id": row["revision_id"],
            "kind": row["kind"],
            "parameters": json.loads(row["parameters_json"]),
            "status": row["status"],
            "executor_id": row["executor_id"],
            "attempt_id": row["attempt_id"],
            "lease_id": row["lease_id"],
            "lease_expires_at": row["lease_expires_at"],
            "attempt_count": row["attempt_count"],
            "provider_policy_sha256": row["provider_policy_sha256"],
            "provider_budget": json.loads(row["provider_budget_json"]),
            "provider_cost_estimate_minor": row["provider_cost_estimate_minor"],
            "runtime_image_sha256": row["runtime_image_sha256"],
            "required_capabilities": json.loads(row["required_capabilities_json"]),
            "required_region": row["required_region"],
            "fingerprints": json.loads(row["fingerprints_json"]),
            "created_at": row["created_at"],
        }

    @staticmethod
    def _job_request_sha256(request: JobCreate) -> str:
        return canonical_sha256(
            {
                "revision_id": str(request.revision_id),
                "kind": request.kind,
                "provider_policy_sha256": request.provider_policy_sha256,
                "provider_budget": request.provider_budget.model_dump(mode="json"),
                "provider_cost_estimate_minor": request.provider_cost_estimate_minor,
                "runtime_image_sha256": request.runtime_image_sha256,
                "required_capabilities": request.required_capabilities,
                "required_region": request.required_region,
                "parameters": request.parameters,
                "fingerprints": request.fingerprints,
            }
        )

    @staticmethod
    def _assert_executor_job_eligible(job: sqlite3.Row, executor: sqlite3.Row) -> None:
        provider_budget = BudgetV1.model_validate(json.loads(job["provider_budget_json"]))
        if (
            provider_budget.max_cost_minor is None
            or int(job["provider_cost_estimate_minor"]) > provider_budget.max_cost_minor
        ):
            raise HTTPException(status_code=409, detail="provider_budget_exceeded")
        capabilities = set(json.loads(executor["capabilities_json"]))
        required = set(json.loads(job["required_capabilities_json"]))
        if (
            (job["kind"] not in capabilities and "*" not in capabilities)
            or not required.issubset(capabilities)
            or (job["required_region"] and job["required_region"] != executor["region"])
        ):
            raise HTTPException(status_code=409, detail="executor_capability_mismatch")

    @staticmethod
    def _issue_job_attempt(
        db: sqlite3.Connection,
        job_id: str,
        executor: sqlite3.Row,
        *,
        ttl_seconds: int,
        claim_idempotency_key: str | None = None,
    ) -> dict[str, str]:
        job = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        if job is None:
            raise HTTPException(status_code=404, detail="job_not_found")
        CloudRepository._assert_executor_job_eligible(job, executor)
        now = datetime.now(UTC)
        executor_expires_at = _timestamp(executor["expires_at"])
        if executor_expires_at <= now:
            raise HTTPException(status_code=409, detail="executor_expired")
        expires_at = min(now + timedelta(seconds=ttl_seconds), executor_expires_at)
        expires_text = expires_at.isoformat().replace("+00:00", "Z")
        attempt_id, lease_id = str(uuid4()), str(uuid4())
        attempt_token = secrets.token_urlsafe(32)
        db.execute(
            "UPDATE jobs SET status='dispatched', executor_id=?, attempt_id=?, lease_id=?, "
            "lease_expires_at=?, attempt_token_hash=?, attempt_token_expires_at=?, "
            "attempt_count=attempt_count+1, claim_idempotency_key=? WHERE id=?",
            (
                str(executor["id"]),
                attempt_id,
                lease_id,
                expires_text,
                _token_hash(attempt_token),
                expires_text,
                claim_idempotency_key,
                job_id,
            ),
        )
        db.execute(
            "INSERT INTO job_attempt_events "
            "(id, job_id, attempt_id, executor_id, lease_id, action, occurred_at) "
            "VALUES (?, ?, ?, ?, ?, 'issued', ?)",
            (str(uuid4()), job_id, attempt_id, str(executor["id"]), lease_id, _now()),
        )
        return {
            "attempt_access_token": attempt_token,
            "attempt_token_expires_at": expires_text,
        }

    @staticmethod
    def _assert_attempt_token(job: sqlite3.Row, attempt_token: str | None) -> None:
        expected_hash = job["attempt_token_hash"]
        if attempt_token is None or expected_hash is None:
            raise HTTPException(status_code=401, detail="attempt_token_required")
        if not hmac.compare_digest(_token_hash(attempt_token), str(expected_hash)):
            raise HTTPException(status_code=401, detail="attempt_token_invalid")
        expires_at = job["attempt_token_expires_at"]
        if expires_at is None or _timestamp(expires_at) <= datetime.now(UTC):
            raise HTTPException(status_code=401, detail="attempt_token_expired")

    def job(
        self,
        workspace_id: str,
        project_id: str,
        actor_id: str,
        request: JobCreate,
        idempotency_key: str,
    ) -> dict[str, Any]:
        project = self.project(workspace_id, project_id, actor_id)
        if str(request.revision_id) != project["current_revision_id"]:
            raise HTTPException(status_code=409, detail="job_revision_is_not_head")
        _assert_portable_document(request.parameters, field="job.parameters")
        if request.fingerprints.get("provider_policy") not in {
            None,
            request.provider_policy_sha256,
        }:
            raise HTTPException(status_code=422, detail="provider_policy_fingerprint_mismatch")
        if request.fingerprints.get("runtime") not in {None, request.runtime_image_sha256}:
            raise HTTPException(status_code=422, detail="runtime_fingerprint_mismatch")
        job_id, created_at = str(uuid4()), _now()
        request_sha256 = self._job_request_sha256(request)
        attempt_credentials: dict[str, str] = {}
        with self._lock, self._connect() as db:
            existing = db.execute(
                "SELECT * FROM jobs WHERE project_id=? AND idempotency_key=?",
                (project_id, idempotency_key),
            ).fetchone()
            if existing is not None:
                if existing["request_sha256"] != request_sha256:
                    raise HTTPException(status_code=409, detail="job_idempotency_conflict")
                return self._job_payload(existing)
            executor = self._select_executor(
                db,
                project["workspace_id"],
                request.kind,
                set(request.required_capabilities),
                request.required_region,
            )
            db.execute(
                "INSERT INTO jobs "
                "(id, project_id, revision_id, actor_id, kind, parameters_json, status, "
                "executor_id, created_at, fingerprints_json, provider_policy_sha256, "
                "provider_budget_json, provider_cost_estimate_minor, runtime_image_sha256, "
                "required_capabilities_json, required_region, idempotency_key, request_sha256) "
                "VALUES (?, ?, ?, ?, ?, ?, 'queued', NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    job_id,
                    project_id,
                    str(request.revision_id),
                    actor_id,
                    request.kind,
                    json.dumps(request.parameters, ensure_ascii=False, sort_keys=True),
                    created_at,
                    json.dumps(request.fingerprints, sort_keys=True),
                    request.provider_policy_sha256,
                    json.dumps(request.provider_budget.model_dump(mode="json"), sort_keys=True),
                    request.provider_cost_estimate_minor,
                    request.runtime_image_sha256,
                    json.dumps(request.required_capabilities),
                    request.required_region,
                    idempotency_key,
                    request_sha256,
                ),
            )
            if executor is not None:
                attempt_credentials = self._issue_job_attempt(
                    db, job_id, executor, ttl_seconds=120
                )
            row = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
            assert row is not None
            payload = self._job_payload(row)
        payload.update(attempt_credentials)
        return payload

    def jobs(self, workspace_id: str, project_id: str, actor_id: str) -> list[dict[str, Any]]:
        self.project(workspace_id, project_id, actor_id)
        with self._connect() as db:
            rows = db.execute(
                "SELECT * FROM jobs WHERE project_id=? ORDER BY created_at, id",
                (project_id,),
            ).fetchall()
        return [self._job_payload(row) for row in rows]

    def get_job(
        self, workspace_id: str, project_id: str, job_id: str, actor_id: str
    ) -> dict[str, Any]:
        self.project(workspace_id, project_id, actor_id)
        with self._connect() as db:
            row = db.execute(
                "SELECT * FROM jobs WHERE id=? AND project_id=?",
                (job_id, project_id),
            ).fetchone()
            result = db.execute(
                "SELECT * FROM job_results WHERE job_id=? "
                "ORDER BY created_at DESC LIMIT 1",
                (job_id,),
            ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="job_not_found")
        payload = self._job_payload(row)
        if result is not None:
            payload["result"] = {
                "attempt_id": result["attempt_id"],
                "status": result["status"],
                "result_schema_version": result["result_schema_version"],
                "result_sha256": result["result_sha256"],
                "result": json.loads(result["result_json"]),
                "output_refs": json.loads(result["output_refs_json"]),
                "output_media_types": json.loads(result["output_media_types_json"]),
                "fingerprints": json.loads(result["fingerprints_json"]),
                "created_at": result["created_at"],
            }
        return payload

    def claim_job(
        self,
        workspace_id: str,
        project_id: str,
        job_id: str,
        actor_id: str,
        request: JobClaimRequest,
        idempotency_key: str,
    ) -> dict[str, Any]:
        self.project(workspace_id, project_id, actor_id)
        with self._lock, self._connect() as db:
            job = db.execute(
                "SELECT * FROM jobs WHERE id=? AND project_id=?", (job_id, project_id)
            ).fetchone()
            if job is None:
                raise HTTPException(status_code=404, detail="job_not_found")
            if job["status"] in {"completed", "failed", "cancelled"}:
                raise HTTPException(status_code=409, detail="job_is_terminal")
            executor = db.execute(
                "SELECT * FROM executors WHERE id=? AND workspace_id=?",
                (str(request.executor_id), workspace_id),
            ).fetchone()
            if executor is None or executor["actor_id"] != actor_id:
                raise HTTPException(status_code=403, detail="executor_scope_mismatch")
            if executor["status"] != "active" or _timestamp(executor["expires_at"]) <= datetime.now(
                UTC
            ):
                raise HTTPException(status_code=409, detail="executor_expired")
            self._assert_executor_job_eligible(job, executor)
            lease_expires_at = job["lease_expires_at"]
            if lease_expires_at is not None and _timestamp(lease_expires_at) > datetime.now(UTC):
                if job["claim_idempotency_key"] == idempotency_key:
                    return self._job_payload(job)
                raise HTTPException(status_code=409, detail="job_attempt_lease_active")
            credentials = self._issue_job_attempt(
                db,
                job_id,
                executor,
                ttl_seconds=request.requested_ttl_seconds,
                claim_idempotency_key=idempotency_key,
            )
            updated = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
            assert updated is not None
            payload = self._job_payload(updated)
        payload.update(credentials)
        return payload

    def job_input(
        self,
        workspace_id: str,
        project_id: str,
        job_id: str,
        attempt_id: str,
        actor_id: str,
        attempt_token: str | None,
    ) -> dict[str, Any]:
        self.project(workspace_id, project_id, actor_id)
        with self._connect() as db:
            job = db.execute(
                "SELECT * FROM jobs WHERE id=? AND project_id=?", (job_id, project_id)
            ).fetchone()
        if job is None:
            raise HTTPException(status_code=404, detail="job_not_found")
        if job["attempt_id"] != attempt_id:
            raise HTTPException(status_code=409, detail="job_attempt_mismatch")
        self._assert_attempt_token(job, attempt_token)
        if job["status"] == "cancelled":
            raise HTTPException(status_code=409, detail="job_cancelled")
        return {
            "job_id": job_id,
            "attempt_id": attempt_id,
            "project_id": project_id,
            "revision_id": job["revision_id"],
            "kind": job["kind"],
            "parameters": json.loads(job["parameters_json"]),
            "provider_policy_sha256": job["provider_policy_sha256"],
            "provider_budget": json.loads(job["provider_budget_json"]),
            "provider_cost_estimate_minor": job["provider_cost_estimate_minor"],
            "runtime_image_sha256": job["runtime_image_sha256"],
            "required_capabilities": json.loads(job["required_capabilities_json"]),
            "required_region": job["required_region"],
            "fingerprints": json.loads(job["fingerprints_json"]),
        }

    def report_job_result(
        self,
        workspace_id: str,
        project_id: str,
        job_id: str,
        actor_id: str,
        report: JobResultReport,
        attempt_token: str | None,
    ) -> dict[str, Any]:
        self.project(workspace_id, project_id, actor_id)
        if canonical_sha256(report.result) != report.result_sha256:
            raise HTTPException(status_code=422, detail="result_hash_mismatch")
        _assert_portable_document(report.result, field="job.result")
        if any(
            not re.fullmatch(r"(?:artifact://)?sha256:[0-9a-f]{64}", item)
            for item in report.output_refs
        ):
            raise HTTPException(status_code=422, detail="invalid_result_reference")
        if set(report.output_media_types) != set(report.output_refs):
            raise HTTPException(status_code=422, detail="result_media_manifest_mismatch")
        created_at = _now()
        with self._lock, self._connect() as db:
            job_row = db.execute(
                "SELECT * FROM jobs WHERE id=? AND project_id=?", (job_id, project_id)
            ).fetchone()
            if job_row is None:
                raise HTTPException(status_code=404, detail="job_not_found")
            self._workspace_access(db, workspace_id, actor_id)
            if job_row["attempt_id"] != str(report.attempt_id):
                raise HTTPException(status_code=409, detail="job_attempt_mismatch")
            if job_row["executor_id"] != str(report.executor_id):
                raise HTTPException(status_code=403, detail="executor_scope_mismatch")
            self._assert_attempt_token(job_row, attempt_token)
            if job_row["status"] == "cancelled":
                raise HTTPException(status_code=409, detail="job_cancelled")
            job_fingerprints = json.loads(job_row["fingerprints_json"])
            if report.fingerprints != job_fingerprints:
                raise HTTPException(status_code=422, detail="job_fingerprint_mismatch")
            result_json = json.dumps(report.result, ensure_ascii=False, sort_keys=True)
            output_refs_json = json.dumps(report.output_refs, ensure_ascii=False)
            output_media_types_json = json.dumps(
                report.output_media_types, ensure_ascii=False, sort_keys=True
            )
            fingerprints_json = json.dumps(report.fingerprints, sort_keys=True)
            existing = db.execute(
                "SELECT * FROM job_results WHERE attempt_id=?", (str(report.attempt_id),)
            ).fetchone()
            if existing is not None:
                exact = (
                    existing["job_id"] == job_id
                    and existing["status"] == report.status
                    and existing["result_schema_version"] == report.result_schema_version
                    and existing["result_sha256"] == report.result_sha256
                    and existing["result_json"] == result_json
                    and existing["output_refs_json"] == output_refs_json
                    and existing["output_media_types_json"] == output_media_types_json
                    and existing["fingerprints_json"] == fingerprints_json
                )
                if not exact:
                    raise HTTPException(status_code=409, detail="attempt_result_conflict")
                return self.get_job(workspace_id, project_id, job_id, actor_id)
            lease_expires_at = job_row["lease_expires_at"]
            if lease_expires_at is None or _timestamp(lease_expires_at) <= datetime.now(UTC):
                raise HTTPException(status_code=409, detail="job_attempt_lease_expired")
            for reference in report.output_refs:
                object_id = reference.removeprefix("artifact://")
                owned = db.execute(
                    "SELECT media_type FROM objects WHERE id=? AND project_id=?",
                    (object_id, project_id),
                ).fetchone()
                if owned is None:
                    raise HTTPException(status_code=422, detail="result_object_not_owned")
                if report.output_media_types[reference] != owned["media_type"]:
                    raise HTTPException(status_code=422, detail="result_media_type_mismatch")
            db.execute(
                "INSERT INTO job_results "
                "(attempt_id, job_id, status, result_sha256, result_json, "
                "output_refs_json, created_at, fingerprints_json, result_schema_version, "
                "output_media_types_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    str(report.attempt_id),
                    job_id,
                    report.status,
                    report.result_sha256,
                    result_json,
                    output_refs_json,
                    created_at,
                    fingerprints_json,
                    report.result_schema_version,
                    output_media_types_json,
                ),
            )
            db.execute("UPDATE jobs SET status=? WHERE id=?", (report.status, job_id))
        updated = self.get_job(workspace_id, project_id, job_id, actor_id)
        updated["output_refs"] = report.output_refs
        return updated

    def cancel_job(
        self, workspace_id: str, project_id: str, job_id: str, actor_id: str
    ) -> dict[str, Any]:
        job = self.get_job(workspace_id, project_id, job_id, actor_id)
        if job["status"] in {"completed", "failed", "cancelled"}:
            return job
        with self._connect() as db:
            db.execute(
                "UPDATE jobs SET status='cancelled', attempt_token_hash=NULL, "
                "attempt_token_expires_at=NULL WHERE id=?",
                (job_id,),
            )
        job["status"] = "cancelled"
        return job


def create_cloud_app(
    db_path: Path | None = None,
    object_root: Path | None = None,
    *,
    auth_mode: Literal["development", "production"] = "development",
    oidc_issuer: str | None = None,
    oidc_audience: str | None = None,
    production_evidence: CloudProductionEvidence | None = None,
) -> FastAPI:
    repository = CloudRepository(
        db_path or Path("cloud-prototype/data/control-plane.db"),
        object_root or Path("cloud-prototype/data/objects"),
    )
    app = FastAPI(title="PPT Video Workbench Cloud Prototype", version="0.1.0")
    app.state.cloud_repository = repository
    app.state.cloud_auth = CloudAuthConfig(auth_mode, oidc_issuer, oidc_audience)
    app.state.cloud_production_evidence = production_evidence or CloudProductionEvidence()
    router = APIRouter(prefix="/v1")

    def actor(x_actor_id: str | None) -> str:
        auth: CloudAuthConfig = app.state.cloud_auth
        if auth.mode == "production":
            if not auth.production_ready:
                raise HTTPException(status_code=503, detail="oidc_not_configured")
            evidence: CloudProductionEvidence = app.state.cloud_production_evidence
            if not evidence.ready:
                raise HTTPException(
                    status_code=503,
                    detail={
                        "code": "production_gate_incomplete",
                        "missing": evidence.missing(),
                    },
                )
            raise HTTPException(status_code=501, detail="oidc_validation_adapter_required")
        return x_actor_id or "dev-user"

    @router.get("/health")
    def health() -> dict[str, str]:
        auth: CloudAuthConfig = app.state.cloud_auth
        evidence: CloudProductionEvidence = app.state.cloud_production_evidence
        return {
            "status": "ok",
            "mode": "prototype",
            "auth_mode": auth.mode,
            "production_gate": "ready" if evidence.ready else "blocked",
        }

    @router.get("/me")
    def me(x_actor_id: str | None = Header(default=None)) -> dict[str, Any]:
        actor_id = actor(x_actor_id)
        return {
            "user_id": _principal_id(actor_id),
            "display_name": actor_id,
            "memberships": repository.memberships(actor_id),
            "devices": repository.list_devices(actor_id),
        }

    @router.post("/organizations", status_code=201)
    def create_organization(
        payload: OrganizationCreate, x_actor_id: str | None = Header(default=None)
    ) -> dict[str, str]:
        return repository.create_organization(actor(x_actor_id), payload.name)

    @router.get("/organizations")
    def list_organizations(x_actor_id: str | None = Header(default=None)) -> dict[str, Any]:
        return {"items": repository.list_organizations(actor(x_actor_id)), "next_cursor": None}

    @router.post("/devices", status_code=201)
    def register_device(
        payload: DeviceRegister, x_actor_id: str | None = Header(default=None)
    ) -> dict[str, str]:
        return repository.register_device(actor(x_actor_id), payload)

    @router.get("/devices")
    def list_devices(x_actor_id: str | None = Header(default=None)) -> dict[str, Any]:
        return {"items": repository.list_devices(actor(x_actor_id)), "next_cursor": None}

    @router.delete("/devices/{deviceId}")
    def revoke_device(
        deviceId: UUID, x_actor_id: str | None = Header(default=None)
    ) -> dict[str, str]:
        return repository.revoke_device(actor(x_actor_id), str(deviceId))

    @router.post("/workspaces", status_code=201)
    def create_workspace(
        payload: WorkspaceCreate, x_actor_id: str | None = Header(default=None)
    ) -> dict[str, Any]:
        return repository.create_workspace(
            actor(x_actor_id),
            payload.name,
            str(payload.organization_id) if payload.organization_id else None,
        )

    @router.get("/workspaces")
    def list_workspaces(x_actor_id: str | None = Header(default=None)) -> dict[str, Any]:
        return {"items": repository.list_workspaces(actor(x_actor_id)), "next_cursor": None}

    @router.get("/workspaces/{workspaceId}/members")
    def list_members(
        request: Request, x_actor_id: str | None = Header(default=None)
    ) -> dict[str, Any]:
        return {
            "items": repository.list_members(workspace_id(request), actor(x_actor_id)),
            "next_cursor": None,
        }

    @router.post("/workspaces/{workspaceId}/members", status_code=201)
    def add_member(
        request: Request,
        payload: MemberAdd,
        x_actor_id: str | None = Header(default=None),
    ) -> dict[str, Any]:
        return repository.add_member(workspace_id(request), actor(x_actor_id), payload)

    @router.delete("/workspaces/{workspaceId}/members/{actorId}")
    def revoke_member(
        request: Request,
        actorId: str,
        idempotency_key: str = Header(alias="Idempotency-Key", min_length=1, max_length=200),
        x_actor_id: str | None = Header(default=None),
    ) -> dict[str, Any]:
        del idempotency_key
        return repository.revoke_member(
            workspace_id(request), actor(x_actor_id), actorId
        )

    @router.post("/workspaces/{workspaceId}/service-accounts", status_code=201)
    def create_service_account(
        request: Request,
        payload: ServiceAccountCreate,
        x_actor_id: str | None = Header(default=None),
    ) -> dict[str, str]:
        return repository.create_service_account(
            workspace_id(request), actor(x_actor_id), payload
        )

    @router.get("/workspaces/{workspaceId}/service-accounts")
    def list_service_accounts(
        request: Request, x_actor_id: str | None = Header(default=None)
    ) -> dict[str, Any]:
        return {
            "items": repository.list_service_accounts(
                workspace_id(request), actor(x_actor_id)
            ),
            "next_cursor": None,
        }

    @router.delete("/workspaces/{workspaceId}/service-accounts/{serviceAccountId}")
    def disable_service_account(
        request: Request,
        serviceAccountId: UUID,
        x_actor_id: str | None = Header(default=None),
    ) -> dict[str, str]:
        return repository.disable_service_account(
            workspace_id(request), actor(x_actor_id), str(serviceAccountId)
        )

    def workspace_id(request: Request) -> str:
        return str(request.path_params["workspaceId"])

    def project_id(request: Request) -> str:
        return str(request.path_params["projectId"])

    @router.get("/workspaces/{workspaceId}/projects")
    def list_projects(
        request: Request, x_actor_id: str | None = Header(default=None)
    ) -> dict[str, Any]:
        return {
            "items": repository.list_projects(workspace_id(request), actor(x_actor_id)),
            "next_cursor": None,
        }

    @router.post("/workspaces/{workspaceId}/projects", status_code=201)
    def create_project(
        request: Request, payload: ProjectCreate, x_actor_id: str | None = Header(default=None)
    ) -> dict[str, Any]:
        return repository.create_project(
            workspace_id(request), actor(x_actor_id), payload.name, payload.manifest
        )

    @router.get("/workspaces/{workspaceId}/projects/{projectId}")
    def get_project(
        request: Request, x_actor_id: str | None = Header(default=None)
    ) -> dict[str, Any]:
        return repository.project(workspace_id(request), project_id(request), actor(x_actor_id))

    @router.get("/workspaces/{workspaceId}/projects/{projectId}/revisions")
    def list_revisions(
        request: Request, x_actor_id: str | None = Header(default=None)
    ) -> dict[str, Any]:
        return {
            "items": repository.revisions(
                workspace_id(request), project_id(request), actor(x_actor_id)
            ),
            "next_cursor": None,
        }

    @router.get("/workspaces/{workspaceId}/projects/{projectId}/revisions/{revisionId}")
    def get_revision(
        request: Request,
        revisionId: str,
        response: Response,
        x_actor_id: str | None = Header(default=None),
    ) -> dict[str, Any]:
        revision = repository.revision(
            workspace_id(request), project_id(request), revisionId, actor(x_actor_id)
        )
        response.headers["ETag"] = revision["content_sha256"]
        return revision

    @router.get("/workspaces/{workspaceId}/projects/{projectId}/operations")
    def list_operations(
        request: Request,
        cursor: str | None = Query(default=None),
        x_device_id: str | None = Header(default=None, alias="X-Device-ID"),
        x_actor_id: str | None = Header(default=None),
    ) -> dict[str, Any]:
        actor_id = actor(x_actor_id)
        repository.assert_active_device(actor_id, x_device_id)
        return {
            "items": repository.operations(
                workspace_id(request), project_id(request), actor_id, cursor
            ),
            "next_cursor": None,
        }

    @router.post("/workspaces/{workspaceId}/projects/{projectId}/operations", status_code=201)
    def append_operation(
        request: Request,
        payload: SyncOperation,
        response: Response,
        x_device_id: str | None = Header(default=None, alias="X-Device-ID"),
        x_actor_id: str | None = Header(default=None),
    ) -> dict[str, Any]:
        actor_id = actor(x_actor_id)
        repository.assert_active_device(actor_id, x_device_id)
        result = repository.append_operation(
            workspace_id(request), project_id(request), actor_id, payload
        )
        response.headers["Operation-Id"] = result["operation_id"]
        return result

    @router.get("/workspaces/{workspaceId}/projects/{projectId}/conflicts")
    def list_sync_conflicts(
        request: Request,
        x_device_id: str | None = Header(default=None, alias="X-Device-ID"),
        x_actor_id: str | None = Header(default=None),
    ) -> dict[str, Any]:
        actor_id = actor(x_actor_id)
        repository.assert_active_device(actor_id, x_device_id)
        return {
            "items": repository.sync_conflicts(
                workspace_id(request), project_id(request), actor_id
            ),
            "next_cursor": None,
        }

    @router.post(
        "/workspaces/{workspaceId}/projects/{projectId}/conflicts/{conflictId}/resolve"
    )
    def resolve_sync_conflict(
        request: Request,
        conflictId: str,
        payload: SyncConflictResolution,
        idempotency_key: str = Header(alias="Idempotency-Key", min_length=1, max_length=200),
        x_device_id: str | None = Header(default=None, alias="X-Device-ID"),
        x_actor_id: str | None = Header(default=None),
    ) -> dict[str, Any]:
        del idempotency_key
        actor_id = actor(x_actor_id)
        repository.assert_active_device(actor_id, x_device_id)
        return repository.resolve_sync_conflict(
            workspace_id(request),
            project_id(request),
            conflictId,
            actor_id,
            payload,
        )

    @router.post("/workspaces/{workspaceId}/projects/{projectId}/objects/uploads", status_code=201)
    def initiate_upload(
        request: Request, payload: InitiateUpload, x_actor_id: str | None = Header(default=None)
    ) -> dict[str, Any]:
        return repository.initiate_upload(
            workspace_id(request), project_id(request), actor(x_actor_id), payload.object
        )

    @router.put(
        "/workspaces/{workspaceId}/projects/{projectId}/objects/uploads/{uploadId}/parts/{partNumber}"
    )
    async def upload_part(
        request: Request,
        uploadId: str,
        partNumber: int,
        x_actor_id: str | None = Header(default=None),
    ) -> dict[str, Any]:
        return repository.upload_part(
            workspace_id(request),
            project_id(request),
            actor(x_actor_id),
            uploadId,
            partNumber,
            await request.body(),
        )

    @router.post(
        "/workspaces/{workspaceId}/projects/{projectId}/objects/uploads/{uploadId}/complete",
        status_code=201,
    )
    def complete_upload(
        request: Request,
        uploadId: str,
        payload: CompleteUpload,
        x_actor_id: str | None = Header(default=None),
    ) -> dict[str, Any]:
        return repository.complete_upload(
            workspace_id(request), project_id(request), actor(x_actor_id), uploadId, payload.parts
        )

    @router.post("/workspaces/{workspaceId}/projects/{projectId}/objects/{objectId}/download")
    def authorize_download(
        request: Request, objectId: str, x_actor_id: str | None = Header(default=None)
    ) -> dict[str, Any]:
        return repository.authorize_download(
            workspace_id(request), project_id(request), actor(x_actor_id), objectId
        )

    @router.get("/workspaces/{workspaceId}/projects/{projectId}/objects/{objectId}/content")
    def download_object_content(
        request: Request, objectId: str, x_actor_id: str | None = Header(default=None)
    ) -> Response:
        content, media_type = repository.read_object(
            workspace_id(request), project_id(request), actor(x_actor_id), objectId
        )
        response = Response(content=content, media_type=media_type)
        response.headers["ETag"] = objectId
        return response

    @router.get("/workspaces/{workspaceId}/projects/{projectId}/comments")
    def list_comments(
        request: Request, x_actor_id: str | None = Header(default=None)
    ) -> dict[str, Any]:
        return {
            "items": repository.comments(
                workspace_id(request), project_id(request), actor(x_actor_id)
            ),
            "next_cursor": None,
        }

    @router.post("/workspaces/{workspaceId}/projects/{projectId}/comments", status_code=201)
    def create_comment(
        request: Request, payload: CommentCreate, x_actor_id: str | None = Header(default=None)
    ) -> dict[str, Any]:
        return repository.comment(
            workspace_id(request),
            project_id(request),
            actor(x_actor_id),
            payload.body,
            payload.anchor,
        )

    @router.get("/workspaces/{workspaceId}/projects/{projectId}/reviews")
    def list_reviews(
        request: Request, x_actor_id: str | None = Header(default=None)
    ) -> dict[str, Any]:
        return {
            "items": repository.reviews(
                workspace_id(request), project_id(request), actor(x_actor_id)
            ),
            "next_cursor": None,
        }

    @router.post("/workspaces/{workspaceId}/projects/{projectId}/reviews", status_code=201)
    def submit_review(
        request: Request, payload: ReviewCreate, x_actor_id: str | None = Header(default=None)
    ) -> dict[str, Any]:
        return repository.review(
            workspace_id(request), project_id(request), actor(x_actor_id), payload
        )

    @router.put("/workspaces/{workspaceId}/projects/{projectId}/lease")
    def lease(
        request: Request, payload: LeaseRequest, x_actor_id: str | None = Header(default=None)
    ) -> dict[str, Any]:
        return repository.lease(
            workspace_id(request), project_id(request), actor(x_actor_id), payload
        )

    @router.delete("/workspaces/{workspaceId}/projects/{projectId}/lease")
    def release_lease(
        request: Request,
        reason: str | None = Query(default=None, min_length=1, max_length=500),
        x_actor_id: str | None = Header(default=None),
    ) -> dict[str, Any]:
        return repository.release_lease(
            workspace_id(request), project_id(request), actor(x_actor_id), reason
        )

    @router.post("/workspaces/{workspaceId}/executors", status_code=201)
    def register_executor(
        request: Request,
        payload: ExecutorRegister,
        x_actor_id: str | None = Header(default=None),
    ) -> dict[str, Any]:
        return repository.register_executor(workspace_id(request), actor(x_actor_id), payload)

    @router.get("/workspaces/{workspaceId}/executors")
    def list_executors(
        request: Request, x_actor_id: str | None = Header(default=None)
    ) -> dict[str, Any]:
        return {
            "items": repository.executors(workspace_id(request), actor(x_actor_id)),
            "next_cursor": None,
        }

    @router.post("/workspaces/{workspaceId}/projects/{projectId}/jobs", status_code=202)
    def create_job(
        request: Request,
        payload: JobCreate,
        idempotency_key: str = Header(alias="Idempotency-Key", min_length=1, max_length=200),
        x_actor_id: str | None = Header(default=None),
    ) -> dict[str, Any]:
        return repository.job(
            workspace_id(request),
            project_id(request),
            actor(x_actor_id),
            payload,
            idempotency_key,
        )

    @router.get("/workspaces/{workspaceId}/projects/{projectId}/jobs")
    def list_jobs(
        request: Request, x_actor_id: str | None = Header(default=None)
    ) -> dict[str, Any]:
        return {
            "items": repository.jobs(
                workspace_id(request), project_id(request), actor(x_actor_id)
            ),
            "next_cursor": None,
        }

    @router.get("/workspaces/{workspaceId}/projects/{projectId}/jobs/{jobId}")
    def get_job(
        request: Request, jobId: str, x_actor_id: str | None = Header(default=None)
    ) -> dict[str, Any]:
        return repository.get_job(
            workspace_id(request), project_id(request), jobId, actor(x_actor_id)
        )

    @router.post(
        "/workspaces/{workspaceId}/projects/{projectId}/jobs/{jobId}/claim",
        status_code=200,
    )
    def claim_job(
        request: Request,
        jobId: str,
        payload: JobClaimRequest,
        idempotency_key: str = Header(alias="Idempotency-Key", min_length=1, max_length=200),
        x_actor_id: str | None = Header(default=None),
    ) -> dict[str, Any]:
        return repository.claim_job(
            workspace_id(request),
            project_id(request),
            jobId,
            actor(x_actor_id),
            payload,
            idempotency_key,
        )

    @router.get(
        "/workspaces/{workspaceId}/projects/{projectId}/jobs/{jobId}/attempts/{attemptId}/input"
    )
    def get_job_attempt_input(
        request: Request,
        jobId: str,
        attemptId: str,
        x_attempt_token: str | None = Header(default=None, alias="X-Attempt-Token"),
        x_actor_id: str | None = Header(default=None),
    ) -> dict[str, Any]:
        return repository.job_input(
            workspace_id(request),
            project_id(request),
            jobId,
            attemptId,
            actor(x_actor_id),
            x_attempt_token,
        )

    @router.post(
        "/workspaces/{workspaceId}/projects/{projectId}/jobs/{jobId}/result",
        status_code=200,
    )
    def report_job_result(
        request: Request,
        jobId: str,
        payload: JobResultReport,
        x_attempt_token: str | None = Header(default=None, alias="X-Attempt-Token"),
        x_actor_id: str | None = Header(default=None),
    ) -> dict[str, Any]:
        return repository.report_job_result(
            workspace_id(request),
            project_id(request),
            jobId,
            actor(x_actor_id),
            payload,
            x_attempt_token,
        )

    @router.delete("/workspaces/{workspaceId}/projects/{projectId}/jobs/{jobId}")
    def cancel_job(
        request: Request, jobId: str, x_actor_id: str | None = Header(default=None)
    ) -> dict[str, Any]:
        return repository.cancel_job(
            workspace_id(request), project_id(request), jobId, actor(x_actor_id)
        )

    app.include_router(router)
    return app
