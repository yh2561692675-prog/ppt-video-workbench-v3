CREATE TABLE schema_migrations (
  version INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  applied_at TEXT NOT NULL
);

CREATE TABLE projects (
  project_id TEXT PRIMARY KEY,
  workbench_project_ref TEXT,
  name TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE jobs (
  job_id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL REFERENCES projects(project_id),
  job_type TEXT NOT NULL,
  schema_version TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN (
    'queued','running','retry_wait','cancelling','succeeded','failed','cancelled'
  )),
  priority INTEGER NOT NULL CHECK(priority BETWEEN 0 AND 100),
  idempotency_key TEXT NOT NULL,
  requested_by TEXT NOT NULL,
  request_json TEXT NOT NULL,
  progress INTEGER NOT NULL DEFAULT 0 CHECK(progress BETWEEN 0 AND 100),
  current_attempt INTEGER NOT NULL DEFAULT 0,
  next_attempt_at TEXT,
  last_error_json TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(job_type, idempotency_key)
);

CREATE TABLE job_attempts (
  attempt_id TEXT PRIMARY KEY,
  job_id TEXT NOT NULL REFERENCES jobs(job_id),
  attempt_number INTEGER NOT NULL,
  status TEXT NOT NULL,
  process_id INTEGER,
  request_path TEXT NOT NULL,
  result_path TEXT NOT NULL,
  stdout_log_path TEXT NOT NULL,
  stderr_log_path TEXT NOT NULL,
  exit_code INTEGER,
  started_at TEXT NOT NULL,
  ended_at TEXT,
  error_json TEXT,
  UNIQUE(job_id, attempt_number)
);

CREATE TABLE events (
  sequence INTEGER PRIMARY KEY AUTOINCREMENT,
  event_id TEXT NOT NULL UNIQUE,
  job_id TEXT NOT NULL REFERENCES jobs(job_id),
  project_id TEXT NOT NULL REFERENCES projects(project_id),
  event_type TEXT NOT NULL,
  source TEXT NOT NULL,
  severity TEXT NOT NULL,
  occurred_at TEXT NOT NULL,
  data_json TEXT NOT NULL
);

CREATE TABLE artifacts (
  artifact_id TEXT PRIMARY KEY,
  job_id TEXT NOT NULL REFERENCES jobs(job_id),
  project_id TEXT NOT NULL REFERENCES projects(project_id),
  logical_name TEXT NOT NULL,
  kind TEXT NOT NULL,
  relative_path TEXT NOT NULL UNIQUE,
  version INTEGER NOT NULL CHECK(version > 0),
  size_bytes INTEGER NOT NULL CHECK(size_bytes >= 0),
  sha256 TEXT NOT NULL CHECK(length(sha256) = 64),
  verified_at TEXT NOT NULL,
  is_current INTEGER NOT NULL CHECK(is_current IN (0, 1)),
  UNIQUE(project_id, logical_name, version)
);

CREATE INDEX idx_jobs_dispatch
  ON jobs(status, next_attempt_at, priority DESC, created_at);
CREATE INDEX idx_events_job_sequence ON events(job_id, sequence);
CREATE UNIQUE INDEX idx_artifacts_current
  ON artifacts(project_id, logical_name) WHERE is_current = 1;
