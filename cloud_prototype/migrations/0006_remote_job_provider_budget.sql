ALTER TABLE jobs ADD COLUMN provider_budget_json TEXT NOT NULL DEFAULT '{"schema_version":1,"timeout_ms":86400000,"max_attempts":1,"max_input_bytes":1073741824,"max_output_bytes":4294967296,"max_cost_minor":0}';
ALTER TABLE jobs ADD COLUMN provider_cost_estimate_minor INTEGER NOT NULL DEFAULT 0;
