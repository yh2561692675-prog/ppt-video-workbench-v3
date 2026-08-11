CREATE TABLE IF NOT EXISTS workspaces (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS members (
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    actor_id TEXT NOT NULL,
    role TEXT NOT NULL,
    PRIMARY KEY(workspace_id, actor_id)
);

CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id),
    name TEXT NOT NULL,
    current_revision_id TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS revisions (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id),
    sequence INTEGER NOT NULL,
    parent_id TEXT,
    content_hash TEXT NOT NULL,
    manifest_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(project_id, sequence)
);

CREATE TABLE IF NOT EXISTS operations (
    id TEXT PRIMARY KEY,
    idempotency_key TEXT UNIQUE NOT NULL,
    project_id TEXT NOT NULL REFERENCES projects(id),
    actor_id TEXT NOT NULL,
    base_revision_id TEXT NOT NULL,
    revision_id TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS objects (
    id TEXT NOT NULL,
    project_id TEXT NOT NULL REFERENCES projects(id),
    size_bytes INTEGER NOT NULL,
    media_type TEXT NOT NULL,
    classification TEXT NOT NULL,
    path TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY(id, project_id)
);

CREATE TABLE IF NOT EXISTS uploads (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id),
    object_id TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    media_type TEXT NOT NULL,
    classification TEXT NOT NULL,
    status TEXT NOT NULL,
    expires_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS comments (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id),
    actor_id TEXT NOT NULL,
    body TEXT NOT NULL,
    anchor_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    resolved INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS reviews (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id),
    revision_id TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    decision TEXT NOT NULL,
    note TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS leases (
    project_id TEXT PRIMARY KEY,
    lease_id TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    client_id TEXT NOT NULL,
    expires_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id),
    revision_id TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    parameters_json TEXT NOT NULL,
    status TEXT NOT NULL,
    executor_id TEXT,
    created_at TEXT NOT NULL,
    fingerprints_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS job_results (
    attempt_id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL REFERENCES jobs(id),
    status TEXT NOT NULL,
    result_sha256 TEXT NOT NULL,
    result_json TEXT NOT NULL,
    output_refs_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    fingerprints_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS executors (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id),
    actor_id TEXT NOT NULL,
    platform TEXT NOT NULL,
    capabilities_json TEXT NOT NULL,
    region TEXT NOT NULL,
    status TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    capability_snapshot_json TEXT NOT NULL DEFAULT '{}'
);
