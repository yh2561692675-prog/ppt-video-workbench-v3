ALTER TABLE jobs ADD COLUMN attempt_id TEXT;
ALTER TABLE jobs ADD COLUMN lease_id TEXT;
ALTER TABLE jobs ADD COLUMN lease_expires_at TEXT;
ALTER TABLE jobs ADD COLUMN attempt_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE jobs ADD COLUMN attempt_token_hash TEXT;
ALTER TABLE jobs ADD COLUMN attempt_token_expires_at TEXT;
ALTER TABLE jobs ADD COLUMN provider_policy_sha256 TEXT NOT NULL DEFAULT 'sha256:0000000000000000000000000000000000000000000000000000000000000000';
ALTER TABLE jobs ADD COLUMN runtime_image_sha256 TEXT NOT NULL DEFAULT 'sha256:0000000000000000000000000000000000000000000000000000000000000000';
ALTER TABLE jobs ADD COLUMN required_capabilities_json TEXT NOT NULL DEFAULT '[]';
ALTER TABLE jobs ADD COLUMN required_region TEXT;
ALTER TABLE jobs ADD COLUMN idempotency_key TEXT;
ALTER TABLE jobs ADD COLUMN request_sha256 TEXT;
ALTER TABLE jobs ADD COLUMN claim_idempotency_key TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS jobs_project_idempotency_key
ON jobs(project_id, idempotency_key)
WHERE idempotency_key IS NOT NULL;

ALTER TABLE job_results ADD COLUMN result_schema_version INTEGER NOT NULL DEFAULT 1;
ALTER TABLE job_results ADD COLUMN output_media_types_json TEXT NOT NULL DEFAULT '{}';

ALTER TABLE executors ADD COLUMN gpu_label TEXT;
ALTER TABLE executors ADD COLUMN office_capability TEXT NOT NULL DEFAULT 'none';

CREATE TABLE IF NOT EXISTS job_attempt_events (
    id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    attempt_id TEXT NOT NULL,
    executor_id TEXT NOT NULL REFERENCES executors(id),
    lease_id TEXT NOT NULL,
    action TEXT NOT NULL,
    occurred_at TEXT NOT NULL
);
