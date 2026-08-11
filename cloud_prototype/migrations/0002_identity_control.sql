CREATE TABLE IF NOT EXISTS organizations (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    owner_actor_id TEXT NOT NULL,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL
);

ALTER TABLE workspaces ADD COLUMN organization_id TEXT REFERENCES organizations(id);
ALTER TABLE workspaces ADD COLUMN created_by TEXT NOT NULL DEFAULT '00000000-0000-0000-0000-000000000000';

ALTER TABLE members ADD COLUMN membership_version INTEGER NOT NULL DEFAULT 1;
ALTER TABLE members ADD COLUMN created_at TEXT NOT NULL DEFAULT '1970-01-01T00:00:00Z';

CREATE TABLE IF NOT EXISTS devices (
    id TEXT PRIMARY KEY,
    actor_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    name TEXT NOT NULL,
    platform TEXT NOT NULL,
    status TEXT NOT NULL,
    registered_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS service_accounts (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    created_by TEXT NOT NULL,
    UNIQUE(workspace_id, name)
);
