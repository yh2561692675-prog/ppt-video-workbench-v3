import type { EffectPlanV2 } from '../../../../remotion/src/types';

export type NodeStatus =
  | 'not_started'
  | 'running'
  | 'needs_confirmation'
  | 'completed'
  | 'failed'
  | 'paused';

export interface Project {
  schema_version: 1;
  id: string;
  name: string;
  project_dir: string;
  created_at: string;
  updated_at: string;
  current_step: number;
  status: NodeStatus;
  pages: NarrationPage[];
  jobs: unknown[];
  source_files: SourceFile[];
  audit_log: unknown[];
  matches: PageMatch[];
  page_extractions?: PageExtraction[];
  audio_import?: AudioImportRecord | null;
  transcript?: Transcript | null;
  audio_differences?: AudioDifference[];
  audio_timeline?: AudioTimelineRecord | null;
  preflight_report?: PreflightReport | null;
  preflight_history?: string[];
}

export interface AudioTimelineRecord {
  id: string;
  version: number;
  duration_ms: number;
  min_page_ms: number;
  boundaries: Array<{ id: string; time_ms: number }>;
  segments: Array<{ page_id: string; start_ms: number; end_ms: number }>;
}

export interface AudioGateResult {
  allowed: boolean;
  reasons: Array<{ code: string; message: string; page_id: string; action: string }>;
}

export interface VideoPreflightIssue {
  code: string;
  message: string;
  action: string;
  page_id: string | null;
  blocking: boolean;
}

export interface VideoPreflight {
  allowed: boolean;
  issues: VideoPreflightIssue[];
  placements: Array<{
    position: 'top' | 'middle' | 'bottom' | 'fallback-panel';
    panel: boolean;
    reason: string | null;
  }>;
  props?: ProjectVideoProps | null;
}

export type PreflightIssueLevel = 'blocking' | 'confirmation' | 'required_warning' | 'info';

export interface PreflightIssue {
  issue_id: string;
  check: string;
  code: string;
  level: PreflightIssueLevel;
  message: string;
  action: string;
  location: {
    page_id: string | null;
    job_id: string | null;
    node: string | null;
    relative_path: string | null;
  };
  fingerprint: string;
  blocking: boolean;
  confirmed: boolean;
  confirmed_by: string | null;
  confirmed_at: string | null;
}

export interface PreflightReport {
  id: string;
  project_id: string;
  checked_at: string;
  scope: string[];
  input_fingerprint: string;
  check_fingerprints: Record<string, string>;
  issues: PreflightIssue[];
  allowed: boolean;
  snapshot_path: string | null;
  reused_checks: string[];
  executed_checks: string[];
}

export interface CleanupPlan {
  id: string;
  project_id: string;
  relative_paths: string[];
  bytes_reclaimable: number;
  affected_nodes: string[];
  protected_paths: string[];
  confirmation_token: string;
  created_at: string;
}

export interface CleanupResult {
  plan_id: string;
  deleted_paths: string[];
  bytes_reclaimed: number;
  affected_nodes: string[];
}

export interface ProjectVideoProps {
  schema_version: 1 | 2;
  project_id: string;
  width: 1920 | 1080;
  height: 1080 | 1920;
  fps: 30;
  duration_ms: number;
  template_version: string;
  reduced_motion: boolean;
  pages: Array<{
    page_id: string;
    page_order: number;
    title: string;
    image_path: string;
    audio_path: string;
    start_ms: number;
    end_ms: number;
    subtitle_cue_ids: string[];
    effect_plan?: EffectPlanV2 | null;
    effect_plan_revision?: number | null;
    effect_plan_hash?: string | null;
  }>;
  subtitles: Array<{
    id: string;
    page_id: string;
    page_order: number;
    start_ms: number;
    end_ms: number;
    text: string;
    source_word_indexes: number[];
  }>;
  subtitle_placements: Array<{
    page_id: string;
    position: 'top' | 'middle' | 'bottom' | 'fallback-panel';
    rect: { x: number; y: number; width: number; height: number };
    panel: boolean;
    reason: string | null;
  }>;
  catalog_version?: string | null;
}

export interface EffectWorkspacePage {
  page_id: string;
  page_order: number;
  title: string | null;
  record: {
    revision: number;
    plan: Record<string, unknown>;
    plan_hash: string;
    status: 'ready' | 'fallback' | 'stale' | 'invalid';
    locked: boolean;
  } | null;
}

export interface EffectWorkspace {
  policy: { aspect_ratio: '16:9' | '9:16'; automatic_generation_enabled: boolean };
  catalog_version: string;
  pages: EffectWorkspacePage[];
}

export interface VideoExportResult {
  mp4_relative_path: string;
  package_relative_path: string;
  duration_ms: number;
  width: number;
  height: number;
  video_codec: string;
  audio_codec: string;
  artifact_count: number;
  cached_pages: number;
}

export interface HeyGenProfile {
  id: string;
  name: string;
  base_url: string;
  base_url_digest: string;
  has_api_key: boolean;
  created_at: string;
  updated_at: string;
  last_used_at: string | null;
}

export interface HeyGenVoice {
  voice_id: string;
  name: string;
  language: string;
  gender: string;
  support_pause: boolean;
  support_locale: boolean;
  preview_audio_url: string | null;
}

export interface AudioDifference {
  id: string;
  page_id: string;
  kind: 'omission' | 'addition' | 'misread' | 'uncertain';
  expected: string;
  actual: string;
  start_ms: number;
  end_ms: number;
  confidence: number;
  status: 'pending' | 'resolved';
  resolution: 'accept_recording' | 'change_narration' | 'reimport' | null;
  resolved_at: string | null;
}

export interface TranscriptWord {
  text: string;
  start_ms: number;
  end_ms: number;
  confidence: number;
}

export interface Transcript {
  segments: Array<{ text: string; start_ms: number; end_ms: number; words: TranscriptWord[] }>;
  words: TranscriptWord[];
  detected_language: string;
  model: string;
  device: string;
  created_at: string;
}

export interface SubtitleTimelineRecord {
  version: number;
  duration_ms: number;
  cues: Array<{
    id: string;
    page_id: string;
    page_order: number;
    start_ms: number;
    end_ms: number;
    text: string;
    source_word_indexes: number[];
  }>;
}

export interface AudioImportRecord {
  id: string;
  original_relative_path: string;
  normalized_relative_path: string;
  duration_ms: number;
  sample_rate: number;
  channels: number;
  sha256: string;
  peak_dbfs: number;
  silence_ratio: number;
  silence_intervals_ms: Array<[number, number]>;
  needs_confirmation: boolean;
  imported_at: string;
}

export interface AudioAsset {
  page_id: string;
  relative_path: string;
  duration_ms: number;
  source: 'heygen';
  cache_key: string;
  voice_id: string;
  request_id: string;
  cached: boolean;
}

export interface PageAudio {
  id: string;
  status: NodeStatus;
  source: 'local' | 'heygen';
  relative_path: string | null;
  duration_ms: number | null;
  cache_key: string | null;
  narration_revision_id: string | null;
  voice_id: string | null;
  remote_request_id: string | null;
}

export interface NarrationPage {
  id: string;
  order: number;
  title: string | null;
  narration: {
    revision_id: string;
    text: string;
    version: number;
    source_refs: string[];
    status: NodeStatus;
  } | null;
  audio?: PageAudio | null;
}

export type NarrationImportMethod = 'page_number' | 'page_title' | 'sequential';

export interface NarrationImportAssignment {
  page_id: string;
  page_order: number;
  page_title: string | null;
  text: string;
  method: NarrationImportMethod;
  warning: string | null;
}

export interface NarrationImportPreview {
  source_name: string;
  assignments: NarrationImportAssignment[];
}

export interface PageExtraction {
  id: string;
  order: number;
  text: string;
  title: string | null;
  preview_path: string | null;
}

export interface NarrationRevision {
  id: string;
  page_id: string;
  version: number;
  text: string;
  author: string;
  source_refs: string[];
  insufficiencies: string[];
  warnings: string[];
  parent_revision_id: string | null;
  restored_from_revision_id: string | null;
  created_at: string;
  character_count: number;
  estimated_duration_seconds: number;
}

export interface NarrationGateResult {
  allowed: boolean;
  reasons: Array<{ code: string; message: string; page_id: string; action: string }>;
}

export interface MatchCandidate {
  outline_ref: string;
  outline_title: string;
  outline_text: string;
  score: number;
  weights: { page_order: number; title: number; keywords: number; body: number };
  components: { page_order: number; title: number; keywords: number; body: number };
}

export interface PageMatch {
  page_id: string;
  page_order: number;
  page_title: string | null;
  page_text: string;
  preview_path: string | null;
  selected_outline_ref: string | null;
  score: number;
  needs_confirmation: boolean;
  conflicts: string[];
  decision_source: 'deterministic_rules' | 'manual';
  candidates: MatchCandidate[];
}

export interface MaterialProcessingResult {
  cached: boolean;
  cache_key: string;
  pages: unknown[];
  matches: PageMatch[];
}

export interface SourceFile {
  id: string;
  kind: 'docx' | 'pptx' | 'pdf' | 'image';
  original_name: string;
  safe_name: string;
  copied_path: string;
  sha256: string;
  size: number;
  modified_at: string;
  image_order: number | null;
}

export interface LlmProfile {
  id: string;
  name: string;
  base_url: string;
  base_url_digest: string;
  model: string;
  has_api_key: boolean;
  created_at: string;
  updated_at: string;
  last_used_at: string | null;
}

export interface UpdateCandidate {
  version: string;
  channel: string;
  notes: string;
  size: number;
  sha256: string;
  package_relative_path: string;
}

export interface UpdateState {
  current_version: string;
  previous_version: string | null;
  staged_version: string | null;
  status: 'idle' | 'staged' | 'applied' | 'rolled_back';
  updated_at: string | null;
}

export type DiagnosticStatus = 'green' | 'yellow' | 'red';

export type DiagnosticCategory =
  | 'ENVIRONMENT'
  | 'CONFIGURATION'
  | 'AUTHENTICATION'
  | 'NETWORK'
  | 'PROVIDER'
  | 'INPUT'
  | 'PROCESSING'
  | 'STORAGE'
  | 'QA'
  | 'INTERNAL';

export interface DiagnosticCheck {
  check_id: string;
  label: string;
  status: DiagnosticStatus;
  category: DiagnosticCategory;
  code: string;
  summary: string;
  impact: string;
  remediation: string;
  evidence: Record<string, unknown>;
}

export interface DiagnosticReport {
  report_id: string;
  checked_at: string;
  overall_status: DiagnosticStatus;
  summary: Record<DiagnosticStatus, number>;
  checks: DiagnosticCheck[];
}

export interface DiagnosticPackage {
  report_id: string;
  relative_path: string;
  sha256: string;
  size_bytes: number;
}

interface Envelope<T> {
  data: T;
  error: null | { code: string; message: string; action?: string };
  request_id: string;
}

export class ApiRequestError extends Error {
  readonly code: string;
  readonly action: string;
  readonly status: number;

  constructor(code: string, message: string, action: string, status: number) {
    super(message);
    this.name = 'ApiRequestError';
    this.code = code;
    this.action = action;
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const isFormData = init?.body instanceof FormData;
  const response = await fetch(path, {
    ...init,
    headers: { ...(isFormData ? {} : { 'Content-Type': 'application/json' }), ...init?.headers },
  });
  const contentType = response.headers.get('content-type') ?? '';
  if (!contentType.toLowerCase().includes('application/json')) {
    const text = await response.text();
    if (!response.ok) {
      throw new ApiRequestError(
        'request_failed',
        `服务端错误（HTTP ${response.status}）：${text || response.statusText}`,
        '请稍后重试',
        response.status,
      );
    }
    throw new ApiRequestError(
      'invalid_response',
      '服务端返回了无法识别的响应。',
      '请稍后重试',
      response.status,
    );
  }
  const body = (await response.json()) as Envelope<T>;
  if (!response.ok || body.error) {
    throw new ApiRequestError(
      body.error?.code ?? 'request_failed',
      body.error?.message ?? `请求失败（${response.status}）`,
      body.error?.action ?? '请稍后重试',
      response.status,
    );
  }
  return body.data;
}

export const api = {
  listProjects: () => request<Project[]>('/api/projects'),
  getProject: (id: string) => request<Project>(`/api/projects/${id}`),
  createProject: (name: string) =>
    request<Project>('/api/projects', { method: 'POST', body: JSON.stringify({ name }) }),
  setStep: (id: string, step: number) =>
    request<Project>(`/api/projects/${id}/step`, {
      method: 'PATCH',
      body: JSON.stringify({ step }),
    }),
  pause: (id: string) => request<Project>(`/api/projects/${id}/pause`, { method: 'POST' }),
  resume: (id: string) => request<Project>(`/api/projects/${id}/resume`, { method: 'POST' }),
  disk: () => request<{ total: number; used: number; free: number }>('/api/system/disk'),
  importSources: (id: string, files: File[]) => {
    const form = new FormData();
    files.forEach((file) => form.append('files', file));
    return request<SourceFile[]>(`/api/projects/${id}/sources`, { method: 'POST', body: form });
  },
  importAudio: (id: string, file: File) => {
    const form = new FormData();
    form.append('file', file);
    return request<AudioImportRecord>(`/api/projects/${id}/audio/import`, {
      method: 'POST',
      body: form,
    });
  },
  transcriptionDevices: (id: string) =>
    request<Array<'cpu' | 'cuda'>>(`/api/projects/${id}/audio/transcription-devices`),
  transcribeAudio: (id: string, device: 'cpu' | 'cuda' = 'cpu') =>
    request<Transcript>(`/api/projects/${id}/audio/transcribe`, {
      method: 'POST',
      body: JSON.stringify({ device }),
    }),
  compareAudioDifferences: (id: string) =>
    request<AudioDifference[]>(`/api/projects/${id}/audio/differences/compare`, {
      method: 'POST',
    }),
  resolveAudioDifference: (id: string, differenceId: string, resolution: string) =>
    request<AudioDifference>(`/api/projects/${id}/audio/differences/${differenceId}`, {
      method: 'PATCH',
      body: JSON.stringify({ resolution }),
    }),
  updateAudioBoundary: (id: string, boundaryId: string, timeMs: number, version: number) =>
    request<AudioTimelineRecord>(`/api/projects/${id}/audio/timeline/${boundaryId}`, {
      method: 'PATCH',
      body: JSON.stringify({ time_ms: timeMs, version }),
    }),
  buildAudioTimeline: (id: string) =>
    request<AudioTimelineRecord>(`/api/projects/${id}/audio/timeline/build`, {
      method: 'POST',
    }),
  buildSubtitles: (id: string) =>
    request<SubtitleTimelineRecord>(`/api/projects/${id}/subtitles/build`, { method: 'POST' }),
  audioGate: (id: string) => request<AudioGateResult>(`/api/projects/${id}/audio/gate`),
  videoPreflight: (id: string, settings?: { reduced_motion: boolean }) =>
    request<VideoPreflight>(`/api/projects/${id}/video/preflight`, {
      method: 'POST',
      ...(settings ? { body: JSON.stringify(settings) } : {}),
    }),
  videoPreview: (id: string) => request<VideoPreflight>(`/api/projects/${id}/video/preview`),
  videoRender: (id: string) =>
    request<VideoExportResult>(`/api/projects/${id}/video/render`, { method: 'POST' }),
  effectWorkspace: (id: string) =>
    request<EffectWorkspace>(`/api/projects/${id}/effects`),
  effectCatalog: (id: string) =>
    request<{ catalog_version: string; templates: Array<{ name: string; internal: boolean }> }>(
      `/api/projects/${id}/effects/catalog`,
    ),
  generateEffects: (id: string, pageIds?: string[]) =>
    request<{ changed_page_ids: string[]; skipped_page_ids: string[]; blocked_page_ids: string[] }>(
      `/api/projects/${id}/effects/generate`,
      { method: 'POST', body: JSON.stringify({ page_ids: pageIds ?? null, force: false }) },
    ),
  preflight: (id: string, scope?: string[]) =>
    request<PreflightReport>(`/api/projects/${id}/preflight`, {
      method: 'POST',
      ...(scope ? { body: JSON.stringify({ scope }) } : {}),
    }),
  getPreflight: (id: string) => request<PreflightReport>(`/api/projects/${id}/preflight`),
  confirmPreflightIssue: (id: string, issueId: string, actor: string, note: string) =>
    request<PreflightReport>(`/api/projects/${id}/issues/${issueId}/confirm`, {
      method: 'POST',
      body: JSON.stringify({ actor, note }),
    }),
  preflightReportUrl: (id: string) => `/api/projects/${id}/preflight/report?format=markdown`,
  render: (id: string) =>
    request<VideoExportResult>(`/api/projects/${id}/render`, { method: 'POST' }),
  estimateCleanup: (id: string, selection?: string[]) =>
    request<CleanupPlan>(`/api/projects/${id}/storage/cleanup/estimate`, {
      method: 'POST',
      ...(selection ? { body: JSON.stringify({ selection }) } : {}),
    }),
  executeCleanup: (projectId: string, planId: string, confirmationToken: string) =>
    request<CleanupResult>(`/api/projects/${projectId}/storage/cleanup/execute`, {
      method: 'POST',
      body: JSON.stringify({ plan_id: planId, confirmation_token: confirmationToken }),
    }),
  createHeyGenProfile: (profile: { name: string; base_url: string; api_key: string }) =>
    request<HeyGenProfile>('/api/settings/heygen-profiles', {
      method: 'POST',
      body: JSON.stringify(profile),
    }),
  updateHeyGenProfile: (
    profileId: string,
    profile: { name: string; base_url: string; api_key: string },
  ) =>
    request<HeyGenProfile>(`/api/settings/heygen-profiles/${profileId}`, {
      method: 'PATCH',
      body: JSON.stringify(profile),
    }),
  listHeyGenProfiles: () => request<HeyGenProfile[]>('/api/settings/heygen-profiles'),
  listHeyGenVoices: (profileId: string) =>
    request<HeyGenVoice[]>(`/api/settings/heygen-profiles/${profileId}/voices`),
  previewHeyGenVoice: (profileId: string, voiceId: string, text: string) =>
    request<{ request_id: string; audio_url: string; duration: number }>(
      `/api/settings/heygen-profiles/${profileId}/preview`,
      { method: 'POST', body: JSON.stringify({ voice_id: voiceId, text }) },
    ),
  synthesizeHeyGenAudio: (
    projectId: string,
    pageId: string,
    input: {
      profile_id: string;
      revision_id: string;
      voice_id: string;
      speed: number;
      replace_existing: boolean;
    },
  ) =>
    request<AudioAsset>(`/api/projects/${projectId}/audio/heygen/${pageId}`, {
      method: 'POST',
      body: JSON.stringify(input),
    }),
  reorderImages: (id: string, orderedIds: string[]) =>
    request<SourceFile[]>(`/api/projects/${id}/sources/image-order`, {
      method: 'PATCH',
      body: JSON.stringify({ ordered_ids: orderedIds }),
    }),
  changeMatch: (projectId: string, pageId: string, outlineRef: string, reason: string) =>
    request<PageMatch>(`/api/projects/${projectId}/matches/${pageId}`, {
      method: 'PATCH',
      body: JSON.stringify({ outline_ref: outlineRef, reason }),
    }),
  parseMaterials: (projectId: string, ocrPolicy: 'never' | 'auto' | 'always' = 'auto') =>
    request<MaterialProcessingResult>(`/api/projects/${projectId}/materials/parse`, {
      method: 'POST',
      body: JSON.stringify({ ocr_policy: ocrPolicy }),
    }),
  createLlmProfile: (profile: { name: string; base_url: string; api_key: string; model: string }) =>
    request<LlmProfile>('/api/settings/llm-profiles', {
      method: 'POST',
      body: JSON.stringify(profile),
    }),
  testLlmProfile: (profileId: string) =>
    request<{ ok: boolean; profile_id: string; model: string }>(
      `/api/settings/llm-profiles/${profileId}/test`,
      { method: 'POST' },
    ),
  listLlmProfiles: () => request<LlmProfile[]>('/api/settings/llm-profiles'),
  updateState: () => request<UpdateState>('/api/updates'),
  checkUpdate: () => request<UpdateCandidate | null>('/api/updates/check'),
  stageUpdate: (packageRelativePath: string) =>
    request<UpdateState>('/api/updates/stage', {
      method: 'POST',
      body: JSON.stringify({ package_relative_path: packageRelativePath }),
    }),
  applyUpdate: () => request<UpdateState>('/api/updates/apply', { method: 'POST' }),
  rollbackUpdate: () => request<UpdateState>('/api/updates/rollback', { method: 'POST' }),
  runDiagnostics: () => request<DiagnosticReport>('/api/diagnostics/run', { method: 'POST' }),
  latestDiagnostics: () => request<DiagnosticReport>('/api/diagnostics/latest'),
  createDiagnosticPackage: () =>
    request<DiagnosticPackage>('/api/diagnostics/package', { method: 'POST' }),
  listNarrationRevisions: (projectId: string, pageId: string) =>
    request<NarrationRevision[]>(`/api/projects/${projectId}/narrations/${pageId}/revisions`),
  generateNarration: (projectId: string, pageId: string, profileId: string) =>
    request<NarrationRevision>(`/api/projects/${projectId}/narrations/${pageId}/generate`, {
      method: 'POST',
      body: JSON.stringify({ profile_id: profileId }),
    }),
  saveNarrationRevision: (
    projectId: string,
    pageId: string,
    input: {
      text: string;
      author: string;
      expected_revision_id: string | null;
      source_refs?: string[];
    },
  ) =>
    request<NarrationRevision>(`/api/projects/${projectId}/narrations/${pageId}/revisions`, {
      method: 'POST',
      body: JSON.stringify(input),
    }),
  restoreNarrationRevision: (
    projectId: string,
    pageId: string,
    revisionId: string,
    expectedRevisionId: string,
  ) =>
    request<NarrationRevision>(
      `/api/projects/${projectId}/narrations/${pageId}/restore/${revisionId}`,
      {
        method: 'POST',
        body: JSON.stringify({ actor: '规划师', expected_revision_id: expectedRevisionId }),
      },
    ),
  narrationGate: (projectId: string) =>
    request<NarrationGateResult>(`/api/projects/${projectId}/workflow/audio-gate`),
  previewNarrationImport: (projectId: string, file: File) => {
    const form = new FormData();
    form.append('file', file);
    return request<NarrationImportPreview>(`/api/projects/${projectId}/narrations/import/preview`, {
      method: 'POST',
      body: form,
    });
  },
  commitNarrationImport: (
    projectId: string,
    input: {
      source_name: string;
      assignments: Array<{
        page_id: string;
        text: string;
        expected_revision_id: string | null;
        method: NarrationImportMethod;
      }>;
    },
  ) =>
    request<NarrationRevision[]>(`/api/projects/${projectId}/narrations/import/commit`, {
      method: 'POST',
      body: JSON.stringify(input),
    }),
  confirmNarrationsBatch: (
    projectId: string,
    items: Array<{
      page_id: string;
      revision_id: string;
      conflict_resolution?: string;
    }>,
  ) =>
    request<Array<{ id: string; page_id: string }>>(
      `/api/projects/${projectId}/confirmations/batch`,
      { method: 'POST', body: JSON.stringify({ actor: '规划师', items }) },
    ),
};
