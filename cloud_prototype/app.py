from __future__ import annotations

import json
import re
import sqlite3
import threading
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, FastAPI, Header, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from workbench.contracts.p2_platform import canonical_sha256


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _expires(seconds: int) -> str:
    return (datetime.now(UTC) + timedelta(seconds=seconds)).isoformat().replace("+00:00", "Z")


class CloudModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class WorkspaceCreate(CloudModel):
    name: str = Field(min_length=1, max_length=120)


class MemberAdd(CloudModel):
    actor_id: str = Field(min_length=1, max_length=200)
    role: Literal["admin", "editor", "reviewer", "viewer"] = "editor"


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


class InitiateUpload(CloudModel):
    object: dict[str, Any]


class CompleteUpload(CloudModel):
    parts: list[dict[str, Any]] = Field(min_length=1, max_length=10000)


class CommentCreate(CloudModel):
    body: str = Field(min_length=1, max_length=10000)
    anchor: dict[str, Any]


class ReviewCreate(CloudModel):
    revision_id: UUID
    decision: Literal["approved", "changes_requested"]
    note: str | None = Field(default=None, max_length=10000)


class LeaseRequest(CloudModel):
    client_id: UUID
    lease_id: UUID | None = None
    requested_ttl_seconds: int = Field(ge=30, le=900)


class JobCreate(CloudModel):
    revision_id: UUID
    kind: Literal["render", "transcribe", "export"]
    parameters: dict[str, Any] = Field(default_factory=dict)


class ExecutorRegister(CloudModel):
    executor_id: UUID = Field(default_factory=uuid4)
    platform: Literal["windows", "macos", "linux"]
    capabilities: list[str] = Field(min_length=1, max_length=100)
    region: str = Field(min_length=1, max_length=64)
    ttl_seconds: int = Field(default=120, ge=30, le=900)


@dataclass(frozen=True)
class CloudAuthConfig:
    mode: Literal["development", "production"] = "development"
    oidc_issuer: str | None = None
    oidc_audience: str | None = None

    @property
    def production_ready(self) -> bool:
        return self.mode == "production" and bool(self.oidc_issuer and self.oidc_audience)


class CloudRepository:
    """Small SQLite WAL repository with tenant checks in every project query."""

    def __init__(self, db_path: Path, object_root: Path) -> None:
        self.db_path = db_path
        self.object_root = object_root
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
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS workspaces (
                    id TEXT PRIMARY KEY, name TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS members (
                    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
                    actor_id TEXT NOT NULL, role TEXT NOT NULL,
                    PRIMARY KEY(workspace_id, actor_id)
                );
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES workspaces(id),
                    name TEXT NOT NULL, current_revision_id TEXT, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS revisions (
                    id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id),
                    sequence INTEGER NOT NULL, parent_id TEXT, content_hash TEXT NOT NULL,
                    manifest_json TEXT NOT NULL, created_at TEXT NOT NULL,
                    UNIQUE(project_id, sequence)
                );
                CREATE TABLE IF NOT EXISTS operations (
                    id TEXT PRIMARY KEY, idempotency_key TEXT UNIQUE NOT NULL,
                    project_id TEXT NOT NULL REFERENCES projects(id), actor_id TEXT NOT NULL,
                    base_revision_id TEXT NOT NULL, revision_id TEXT NOT NULL,
                    payload_json TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS objects (
                    id TEXT NOT NULL, project_id TEXT NOT NULL REFERENCES projects(id),
                    size_bytes INTEGER NOT NULL, media_type TEXT NOT NULL,
                    classification TEXT NOT NULL,
                    path TEXT NOT NULL, created_at TEXT NOT NULL, PRIMARY KEY(id, project_id)
                );
                CREATE TABLE IF NOT EXISTS uploads (
                    id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id),
                    object_id TEXT NOT NULL, size_bytes INTEGER NOT NULL, media_type TEXT NOT NULL,
                    classification TEXT NOT NULL, status TEXT NOT NULL, expires_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS comments (
                    id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id),
                    actor_id TEXT NOT NULL, body TEXT NOT NULL, anchor_json TEXT NOT NULL,
                    created_at TEXT NOT NULL, resolved INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS reviews (
                    id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id),
                    revision_id TEXT NOT NULL, actor_id TEXT NOT NULL, decision TEXT NOT NULL,
                    note TEXT, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS leases (
                    project_id TEXT PRIMARY KEY, lease_id TEXT NOT NULL, actor_id TEXT NOT NULL,
                    client_id TEXT NOT NULL, expires_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id),
                    revision_id TEXT NOT NULL, actor_id TEXT NOT NULL, kind TEXT NOT NULL,
                    parameters_json TEXT NOT NULL, status TEXT NOT NULL,
                    executor_id TEXT, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS executors (
                    id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES workspaces(id),
                    actor_id TEXT NOT NULL, platform TEXT NOT NULL, capabilities_json TEXT NOT NULL,
                    region TEXT NOT NULL, status TEXT NOT NULL, expires_at TEXT NOT NULL
                );
                """
            )
            columns = {row["name"] for row in db.execute("PRAGMA table_info(jobs)")}
            if "executor_id" not in columns:
                db.execute("ALTER TABLE jobs ADD COLUMN executor_id TEXT")

    def create_workspace(self, actor_id: str, name: str) -> dict[str, Any]:
        workspace_id = str(uuid4())
        created_at = _now()
        with self._lock, self._connect() as db:
            db.execute("INSERT INTO workspaces VALUES (?, ?, ?)", (workspace_id, name, created_at))
            db.execute("INSERT INTO members VALUES (?, ?, 'owner')", (workspace_id, actor_id))
        return {
            "workspace_id": workspace_id,
            "name": name,
            "role": "owner",
            "created_at": created_at,
        }

    def list_workspaces(self, actor_id: str) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT w.id, w.name, w.created_at, m.role FROM workspaces w "
                "JOIN members m ON m.workspace_id=w.id WHERE m.actor_id=? "
                "ORDER BY w.created_at, w.id",
                (actor_id,),
            ).fetchall()
        return [
            {
                "workspace_id": row["id"],
                "name": row["name"],
                "role": row["role"],
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def list_members(self, workspace_id: str, actor_id: str) -> list[dict[str, Any]]:
        with self._connect() as db:
            self._workspace_access(db, workspace_id, actor_id)
            rows = db.execute(
                "SELECT actor_id, role FROM members WHERE workspace_id=? ORDER BY actor_id",
                (workspace_id,),
            ).fetchall()
        return [{"actor_id": row["actor_id"], "role": row["role"]} for row in rows]

    def add_member(self, workspace_id: str, actor_id: str, member: MemberAdd) -> dict[str, str]:
        with self._lock, self._connect() as db:
            role = self._workspace_access(db, workspace_id, actor_id)
            if role not in {"owner", "admin"}:
                raise HTTPException(status_code=403, detail="member_admin_required")
            db.execute(
                "INSERT INTO members VALUES (?, ?, ?) ON CONFLICT(workspace_id, actor_id) "
                "DO UPDATE SET role=excluded.role",
                (workspace_id, member.actor_id, member.role),
            )
        return {"workspace_id": workspace_id, "actor_id": member.actor_id, "role": member.role}

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
            if str(operation.base_revision_id) != project["current_revision_id"]:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": "revision_conflict",
                        "head_revision_id": project["current_revision_id"],
                    },
                )
            parent = db.execute(
                "SELECT * FROM revisions WHERE id=?", (project["current_revision_id"],)
            ).fetchone()
            manifest = json.loads(parent["manifest_json"])
            manifest["last_operation"] = {"kind": operation.kind, "payload": operation.payload}
            revision_id, operation_id = str(uuid4()), str(operation.operation_id)
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
                "UPDATE projects SET current_revision_id=? WHERE id=?", (revision_id, project_id)
            )
            db.execute(
                "INSERT INTO operations VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    operation_id,
                    str(operation.idempotency_key),
                    project_id,
                    actor_id,
                    str(operation.base_revision_id),
                    revision_id,
                    json.dumps(operation.model_dump(mode="json"), separators=(",", ":")),
                    created_at,
                ),
            )
            revision = db.execute("SELECT * FROM revisions WHERE id=?", (revision_id,)).fetchone()
        return {
            "operation_id": operation_id,
            "accepted_attempt_id": str(operation.attempt_id),
            "revision": self._revision_dict(revision),
            "cursor": operation_id,
            "conflict": None,
        }

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
                    "expires_at": expires_at,
                }
            ],
            "expires_at": expires_at,
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
            object_path = self._object_path(project_id, upload["object_id"])
            storage_key = f"{project_id}/{upload['object_id'].removeprefix('sha256:')}"
            object_path.parent.mkdir(parents=True, exist_ok=True)
            object_path.touch(exist_ok=True)
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
        self, workspace_id: str, project_id: str, actor_id: str, body: str, anchor: dict[str, Any]
    ) -> dict[str, Any]:
        self.project(workspace_id, project_id, actor_id)
        comment_id, created_at = str(uuid4()), _now()
        with self._connect() as db:
            db.execute(
                "INSERT INTO comments VALUES (?, ?, ?, ?, ?, ?, 0)",
                (
                    comment_id,
                    project_id,
                    actor_id,
                    body,
                    json.dumps(anchor, separators=(",", ":")),
                    created_at,
                ),
            )
        return {
            "comment_id": comment_id,
            "project_id": project_id,
            "author_id": actor_id,
            "body": body,
            "anchor": anchor,
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
                "author_id": row["actor_id"],
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
        review_id, created_at = str(uuid4()), _now()
        with self._connect() as db:
            db.execute(
                "INSERT INTO reviews VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    review_id,
                    project_id,
                    str(request.revision_id),
                    actor_id,
                    request.decision,
                    request.note,
                    created_at,
                ),
            )
        return {
            "review_id": review_id,
            "project_id": project_id,
            "revision_id": str(request.revision_id),
            "reviewer_id": actor_id,
            "decision": request.decision,
            "note": request.note,
            "created_at": created_at,
        }

    def lease(
        self, workspace_id: str, project_id: str, actor_id: str, request: LeaseRequest
    ) -> dict[str, Any]:
        self.project(workspace_id, project_id, actor_id)
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
                "INSERT OR REPLACE INTO leases VALUES (?, ?, ?, ?, ?)",
                (project_id, lease_id, actor_id, str(request.client_id), expires_at),
            )
        return {
            "lease_id": lease_id,
            "project_id": project_id,
            "holder_user_id": actor_id,
            "client_id": str(request.client_id),
            "acquired_at": _now(),
            "expires_at": expires_at,
        }

    def register_executor(
        self, workspace_id: str, actor_id: str, request: ExecutorRegister
    ) -> dict[str, Any]:
        with self._connect() as db:
            self._workspace_access(db, workspace_id, actor_id)
            expires_at = _expires(request.ttl_seconds)
            db.execute(
                "INSERT OR REPLACE INTO executors VALUES (?, ?, ?, ?, ?, ?, 'active', ?)",
                (
                    str(request.executor_id),
                    workspace_id,
                    actor_id,
                    request.platform,
                    json.dumps(sorted(set(request.capabilities))),
                    request.region,
                    expires_at,
                ),
            )
        return {
            "executor_id": str(request.executor_id),
            "workspace_id": workspace_id,
            "platform": request.platform,
            "capabilities": sorted(set(request.capabilities)),
            "region": request.region,
            "status": "active",
            "expires_at": expires_at,
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
                "status": (
                    row["status"]
                    if datetime.fromisoformat(row["expires_at"].replace("Z", "+00:00")) > now
                    else "expired"
                ),
                "expires_at": row["expires_at"],
            }
            for row in rows
        ]

    @staticmethod
    def _select_executor(db: sqlite3.Connection, workspace_id: str, kind: str) -> str | None:
        rows = db.execute(
            "SELECT id, capabilities_json, expires_at FROM executors "
            "WHERE workspace_id=? AND status='active' ORDER BY id",
            (workspace_id,),
        ).fetchall()
        now = datetime.now(UTC)
        for row in rows:
            if datetime.fromisoformat(row["expires_at"].replace("Z", "+00:00")) <= now:
                continue
            capabilities = set(json.loads(row["capabilities_json"]))
            if kind in capabilities or "*" in capabilities:
                return str(row["id"])
        return None

    def job(
        self, workspace_id: str, project_id: str, actor_id: str, request: JobCreate
    ) -> dict[str, Any]:
        project = self.project(workspace_id, project_id, actor_id)
        if str(request.revision_id) != project["current_revision_id"]:
            raise HTTPException(status_code=409, detail="job_revision_is_not_head")
        job_id, created_at = str(uuid4()), _now()
        with self._connect() as db:
            executor_id = self._select_executor(db, project["workspace_id"], request.kind)
            db.execute(
                "INSERT INTO jobs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    job_id,
                    project_id,
                    str(request.revision_id),
                    actor_id,
                    request.kind,
                    json.dumps(request.parameters),
                    "dispatched" if executor_id else "queued",
                    executor_id,
                    created_at,
                ),
            )
        return {
            "job_id": job_id,
            "project_id": project_id,
            "revision_id": str(request.revision_id),
            "kind": request.kind,
            "status": "dispatched" if executor_id else "queued",
            "executor_id": executor_id,
            "created_at": created_at,
        }

    def jobs(self, workspace_id: str, project_id: str, actor_id: str) -> list[dict[str, Any]]:
        self.project(workspace_id, project_id, actor_id)
        with self._connect() as db:
            rows = db.execute(
                "SELECT id, project_id, revision_id, kind, status, executor_id, "
                "created_at FROM jobs "
                "WHERE project_id=? ORDER BY created_at, id",
                (project_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_job(
        self, workspace_id: str, project_id: str, job_id: str, actor_id: str
    ) -> dict[str, Any]:
        self.project(workspace_id, project_id, actor_id)
        with self._connect() as db:
            row = db.execute(
                "SELECT id, project_id, revision_id, kind, status, executor_id, "
                "created_at FROM jobs "
                "WHERE id=? AND project_id=?",
                (job_id, project_id),
            ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="job_not_found")
        return dict(row)

    def cancel_job(
        self, workspace_id: str, project_id: str, job_id: str, actor_id: str
    ) -> dict[str, Any]:
        job = self.get_job(workspace_id, project_id, job_id, actor_id)
        if job["status"] in {"completed", "failed", "cancelled"}:
            return job
        with self._connect() as db:
            db.execute("UPDATE jobs SET status='cancelled' WHERE id=?", (job_id,))
        job["status"] = "cancelled"
        return job


def create_cloud_app(
    db_path: Path | None = None,
    object_root: Path | None = None,
    *,
    auth_mode: Literal["development", "production"] = "development",
    oidc_issuer: str | None = None,
    oidc_audience: str | None = None,
) -> FastAPI:
    repository = CloudRepository(
        db_path or Path("cloud-prototype/data/control-plane.db"),
        object_root or Path("cloud-prototype/data/objects"),
    )
    app = FastAPI(title="PPT Video Workbench Cloud Prototype", version="0.1.0")
    app.state.cloud_repository = repository
    app.state.cloud_auth = CloudAuthConfig(auth_mode, oidc_issuer, oidc_audience)
    router = APIRouter(prefix="/v1")

    def actor(x_actor_id: str | None) -> str:
        auth: CloudAuthConfig = app.state.cloud_auth
        if auth.mode == "production":
            if not auth.production_ready:
                raise HTTPException(status_code=503, detail="oidc_not_configured")
            raise HTTPException(status_code=501, detail="oidc_validation_adapter_required")
        return x_actor_id or "dev-user"

    @router.get("/health")
    def health() -> dict[str, str]:
        auth: CloudAuthConfig = app.state.cloud_auth
        return {"status": "ok", "mode": "prototype", "auth_mode": auth.mode}

    @router.get("/me")
    def me(x_actor_id: str | None = Header(default=None)) -> dict[str, str]:
        return {"user_id": actor(x_actor_id), "authentication": "development-header"}

    @router.post("/workspaces", status_code=201)
    def create_workspace(
        payload: WorkspaceCreate, x_actor_id: str | None = Header(default=None)
    ) -> dict[str, Any]:
        return repository.create_workspace(actor(x_actor_id), payload.name)

    @router.get("/workspaces")
    def list_workspaces(x_actor_id: str | None = Header(default=None)) -> dict[str, Any]:
        return {"items": repository.list_workspaces(actor(x_actor_id))}

    @router.get("/workspaces/{workspaceId}/members")
    def list_members(
        request: Request, x_actor_id: str | None = Header(default=None)
    ) -> dict[str, Any]:
        return {"items": repository.list_members(workspace_id(request), actor(x_actor_id))}

    @router.post("/workspaces/{workspaceId}/members", status_code=201)
    def add_member(
        request: Request,
        payload: MemberAdd,
        x_actor_id: str | None = Header(default=None),
    ) -> dict[str, str]:
        return repository.add_member(workspace_id(request), actor(x_actor_id), payload)

    def workspace_id(request: Request) -> str:
        return str(request.path_params["workspaceId"])

    def project_id(request: Request) -> str:
        return str(request.path_params["projectId"])

    @router.get("/workspaces/{workspaceId}/projects")
    def list_projects(
        request: Request, x_actor_id: str | None = Header(default=None)
    ) -> dict[str, Any]:
        return {"items": repository.list_projects(workspace_id(request), actor(x_actor_id))}

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
            )
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
        x_actor_id: str | None = Header(default=None),
    ) -> dict[str, Any]:
        return {
            "items": repository.operations(
                workspace_id(request), project_id(request), actor(x_actor_id), cursor
            )
        }

    @router.post("/workspaces/{workspaceId}/projects/{projectId}/operations", status_code=201)
    def append_operation(
        request: Request,
        payload: SyncOperation,
        response: Response,
        x_actor_id: str | None = Header(default=None),
    ) -> dict[str, Any]:
        result = repository.append_operation(
            workspace_id(request), project_id(request), actor(x_actor_id), payload
        )
        response.headers["Operation-Id"] = result["operation_id"]
        return result

    @router.post("/workspaces/{workspaceId}/projects/{projectId}/objects/uploads", status_code=201)
    def initiate_upload(
        request: Request, payload: InitiateUpload, x_actor_id: str | None = Header(default=None)
    ) -> dict[str, Any]:
        return repository.initiate_upload(
            workspace_id(request), project_id(request), actor(x_actor_id), payload.object
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

    @router.get("/workspaces/{workspaceId}/projects/{projectId}/comments")
    def list_comments(
        request: Request, x_actor_id: str | None = Header(default=None)
    ) -> dict[str, Any]:
        return {
            "items": repository.comments(
                workspace_id(request), project_id(request), actor(x_actor_id)
            )
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
        return {"items": repository.executors(workspace_id(request), actor(x_actor_id))}

    @router.post("/workspaces/{workspaceId}/projects/{projectId}/jobs", status_code=202)
    def create_job(
        request: Request, payload: JobCreate, x_actor_id: str | None = Header(default=None)
    ) -> dict[str, Any]:
        return repository.job(
            workspace_id(request), project_id(request), actor(x_actor_id), payload
        )

    @router.get("/workspaces/{workspaceId}/projects/{projectId}/jobs")
    def list_jobs(
        request: Request, x_actor_id: str | None = Header(default=None)
    ) -> dict[str, Any]:
        return {
            "items": repository.jobs(workspace_id(request), project_id(request), actor(x_actor_id))
        }

    @router.get("/workspaces/{workspaceId}/projects/{projectId}/jobs/{jobId}")
    def get_job(
        request: Request, jobId: str, x_actor_id: str | None = Header(default=None)
    ) -> dict[str, Any]:
        return repository.get_job(
            workspace_id(request), project_id(request), jobId, actor(x_actor_id)
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
