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

export interface CloudJobResultV1 {
  attempt_id: UUID;
  executor_id: UUID;
  status: "completed" | "failed";
  result: Record<string, unknown>;
  result_sha256: Sha256;
  output_refs: Array<`artifact://${Sha256}` | Sha256>;
}

/**
 * Explicit bridge to A13. The integer P2 envelope and string core versions are
 * independent namespaces; no client may normalize or coerce these values.
 */
export interface CoreContractCompatibilityV1 {
  schema_version: 1;
  core_contract_set_sha256: "de55cc1090e49b0ab4d7fb6375b4509cb878d5888e8bef54fd00407a34fbebf6";
  job_schema_version: "1.0";
  asset_schema_version: "1.0";
  error_mapping_version: "1.0";
  version_conversion: "none";
}

export type ProviderKind = "llm" | "tts" | "asr" | "ocr" | "avatar" | "renderer";
export type ExecutionMode = "in_process_builtin" | "local_process" | "remote_https";

export interface ProviderCapabilityV1 {
  schema_version: 1;
  capability_id: string;
  modalities: string[];
  languages?: string[];
  models?: string[];
  max_input_bytes?: number | null;
  max_duration_us?: number | null;
  supports_streaming?: boolean;
  supports_cancellation?: boolean;
  supports_idempotency?: boolean;
  supports_word_timestamps?: boolean | null;
  supports_cost_estimate?: boolean;
  data_regions?: string[];
}

export interface ProviderDescriptorV1 {
  schema_version: 1;
  provider_id: string;
  display_name: string;
  kind: ProviderKind;
  adapter_version: string;
  execution_mode: ExecutionMode;
  capabilities: ProviderCapabilityV1[];
  credential_schema_id?: string | null;
  privacy_policy_ref?: string | null;
  enabled?: boolean;
  trust?: "builtin_signed" | "builtin_local_process";
}

export interface ProviderInvocationV1 {
  schema_version: 1;
  operation: OperationContextV1;
  provider_id: string;
  capability_id: string;
  model?: string | null;
  input_refs?: string[];
  parameters?: Record<string, unknown>;
  expected_output_schema: string;
}

export interface ProviderInvocationResultV1 {
  schema_version: 1;
  operation_id: UUID;
  provider_id: string;
  capability_id: string;
  model_resolved?: string | null;
  status: "succeeded" | "failed" | "cancelled" | "degraded";
  output_refs?: string[];
  usage?: Record<string, number | string>;
  estimated_cost?: number | string | null;
  billed_cost?: number | string | null;
  cache_identity: string;
  provider_request_id?: string | null;
  warnings?: string[];
}

export interface ProviderHealthV1 {
  schema_version: 1;
  provider_id: string;
  status: "unknown" | "available" | "degraded" | "disabled" | "incompatible";
  observed_at: string;
  expires_at: string;
  latency_ms_p50?: number | null;
  latency_ms_p95?: number | null;
  error_code?: string | null;
  billed_probe?: boolean;
}

export interface ProviderCostEstimateV1 {
  schema_version: 1;
  provider_id: string;
  capability_id: string;
  currency: string;
  estimated_cost_minor: number;
  price_book_version: string;
  confidence: "exact" | "estimated" | "unknown";
  unit: string;
}

export interface ProviderAuditEventV1 {
  schema_version: 1;
  event_id: UUID;
  operation_id: UUID;
  tenant_id: UUID;
  project_id?: string | null;
  provider_id: string;
  capability_id: string;
  event_kind: "invoke" | "cache_hit" | "failure";
  status: string;
  billed_cost_minor: number;
  occurred_at: string;
  error_code?: string | null;
}

export interface PlatformInfoV1 {
  schema_version: 1;
  platform: "windows" | "macos" | "linux";
  architecture: string;
  runtime_version: string;
  app_version: string;
}

export interface ToolInfoV1 {
  schema_version: 1;
  name: string;
  available: boolean;
  executable_ref?: `runtime://${string}` | `system://${string}` | `unavailable://${string}` | `unknown://${string}` | null;
  version?: string | null;
  source: "bundled" | "supported_system" | "unavailable" | "unknown";
  sha256?: Sha256 | null;
  capabilities?: string[];
}

export interface CapabilityStateV1 {
  schema_version: 1;
  capability_id: string;
  status: "supported" | "missing" | "misconfigured" | "temporarily_unavailable" | "unsupported";
  detail?: string | null;
}

export interface PlatformCapabilitySnapshotV1 {
  schema_version: 1;
  info: PlatformInfoV1;
  capabilities?: string[];
  capability_states?: CapabilityStateV1[];
  tools?: ToolInfoV1[];
  fingerprint: Sha256;
  generated_at: string;
  expires_at: string;
}

export interface CloudObjectRefV1 {
  schema_version: 1;
  object_id: Sha256;
  sha256: Sha256;
  size_bytes: number;
  media_type: string;
  logical_path: string;
  display_name?: string;
  etag?: string;
  scan_status?: "pending" | "clean" | "rejected";
}

export interface CloudProjectRevisionV1 {
  schema_version: 1;
  revision_id: UUID;
  project_id: UUID;
  workspace_id: UUID;
  parent_revision_ids: UUID[];
  manifest_sha256: Sha256;
  content_sha256: Sha256;
  objects: CloudObjectRefV1[];
  created_at: string;
  created_by: UUID;
  message?: string;
}

export type CloudSyncOperationKind =
  | "project.metadata.set"
  | "material.add"
  | "material.remove"
  | "page.insert"
  | "page.move"
  | "page.replace"
  | "page.remove"
  | "timeline.patch"
  | "revision.resolve_conflict";

export interface CloudSyncOperationV1 {
  schema_version: 1;
  operation_id: UUID;
  idempotency_key: UUID;
  attempt_id: UUID;
  workspace_id: UUID;
  project_id: UUID;
  base_revision_id: UUID;
  client_id: UUID;
  client_sequence: number;
  kind: CloudSyncOperationKind;
  payload: Record<string, unknown>;
  payload_sha256: Sha256;
  created_at: string;
}

export * from "./cloud-client.generated";

