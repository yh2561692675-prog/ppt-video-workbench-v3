ALTER TABLE operations ADD COLUMN kind TEXT NOT NULL DEFAULT 'legacy';
ALTER TABLE operations ADD COLUMN target_keys_json TEXT NOT NULL DEFAULT '[]';
ALTER TABLE operations ADD COLUMN conflict_id TEXT;

CREATE TABLE IF NOT EXISTS sync_conflicts (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    operation_id TEXT NOT NULL UNIQUE,
    idempotency_key TEXT NOT NULL UNIQUE,
    actor_id TEXT NOT NULL,
    base_revision_id TEXT NOT NULL,
    head_revision_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    paths_json TEXT NOT NULL,
    operation_json TEXT NOT NULL,
    status TEXT NOT NULL,
    resolution_json TEXT,
    resolved_revision_id TEXT,
    created_at TEXT NOT NULL,
    resolved_at TEXT
);
