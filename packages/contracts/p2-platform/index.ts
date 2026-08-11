export type UUID = string;
export type Sha256 = `sha256:${string}`;

export interface BudgetV1 {
  schema_version: 1;
  timeout_ms: number;
  max_attempts: number;
  max_input_bytes: number;
  max_output_bytes: number;
  max_cost_minor?: number;
}

export interface LogicalResourceRefV1 {
  schema_version: 1;
  tenant_id: UUID;
  resource_type: string;
  resource_id: UUID;
  logical_path?: string;
  revision_id?: UUID;
}

export interface OperationContextV1 {
  schema_version: 1;
  operation_id: UUID;
  idempotency_key: UUID;
  attempt_id: UUID;
  tenant_id: UUID;
  actor_id?: UUID;
  request_kind: string;
  started_at: string;
  deadline_at?: string;
  budget: BudgetV1;
  resource?: LogicalResourceRefV1;
}

export type ErrorCategory = "provider" | "platform" | "sync" | "cloud" | "executor" | "validation";

export interface StructuredErrorV1 {
  schema_version: 1;
  code: string;
  category: ErrorCategory;
  message: string;
  retryable: boolean;
  failover_allowed: boolean;
  user_action: string;
  safe_details: Record<string, string | number | boolean | null>;
  provider_id?: string;
  operation_id: UUID;
  attempt_id?: UUID;
}

