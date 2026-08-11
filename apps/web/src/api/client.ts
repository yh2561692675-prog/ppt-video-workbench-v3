import type { EffectPlanV2 } from '../../../../remotion/src/types';
import type { RenderGraphV2 } from '../../../../remotion/src/render-graph/types';
import type { PresenterSource, PresenterTimeline } from '../features/presenter/api';

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
  presentation_mode?: 'ai_narration' | 'human_presenter';
  presenter_source?: PresenterSource | null;
  presenter_timeline?: PresenterTimeline | null;
  video_export?: VideoExportResult | null;
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

export interface QualityIssue {
  issue_id: string;
  code: string;
  severity: 'P0' | 'P1' | 'P2' | 'P3';
  scope: string;
  message: string;
  action: string;
  start_ms?: number | null;
  end_ms?: number | null;
  page_id?: string | null;
}

export interface QualityReport {
  result: 'pass' | 'pass_with_warnings' | 'blocked';
  issues: QualityIssue[];
  sampled_frames: number[];
  analyzer_versions: Record<string, string>;
  report_path?: string | null;
}

export interface QualityJobRecord {
  job_id: string;
  project_id: string;
  render_job_id: string;
  status: 'running' | 'succeeded' | 'blocked' | 'failed';
  report: QualityReport | null;
  error_code: string | null;
  error: string | null;
  created_at: string;
  updated_at: string;
}

export interface ProductionTimelineRecord {
  schema_version: string;
  project_id: string;
  revision: number;
  fps: number;
  width: number;
  height: number;
  duration_us: number;
  tracks: Array<{
    id: string;
    kind: string;
    name: string;
    order: number;
    muted: boolean;
    locked: boolean;
    clips: Array<{
      id: string;
      track_id: string;
      kind: string;
      start_us: number;
      duration_us: number;
      source_ref: string;
      locked: boolean;
      payload: Record<string, unknown>;
    }>;
  }>;
  markers: Array<{ id: string; start_us: number; label: string; kind: string }>;
  input_fingerprint: string;
  content_hash: string;
}

export interface RenderGraphRecord {
  schema_version: string;
  project_id: string;
  timeline_revision: number;
  duration_us: number;
  content_hash: string;
  nodes: Array<{
    id: string;
    clip_id: string;
    track_id: string;
    kind: string;
    start_us: number;
    end_us: number;
    source_ref: string;
    cache_key: string;
    depends_on: string[];
  }>;
}

export type RenderGraphV2Record = RenderGraphV2;

export interface AssetRecord {
  asset_id: string;
  revision: number;
  project_id: string;
  kind: string;
  content_hash: string;
  relative_object_path: string;
  original_name: string;
  mime_type: string;
  size_bytes: number;
  license: { status: 'unknown' | 'confirmed' | 'expired' | 'blocked'; owner?: string | null };
  tags: string[];
  brand_pack_id?: string | null;
  derived_from?: string | null;
  operation?: string | null;
}

export interface MaterialCollectionRecord {
  schema_version: string;
  collection_id: string;
  revision: number;
  project_id: string;
  outline_mode: 'none' | 'generated' | 'selected' | 'merged';
  merge_policy: 'manual' | 'append' | 'chapter_match';
  documents: Array<{ document_id: string; title: string; role: string; enabled: boolean }>;
  presentations: Array<{
    presentation_id: string;
    title: string;
    enabled: boolean;
    page_count?: number | null;
  }>;
  sections: Array<{
    section_id: string;
    order: number;
    title: string;
    enabled: boolean;
    page_ids: string[];
  }>;
  page_sequence: Array<{
    material_page_id: string;
    source_ref: string;
    order: number;
    title: string;
    section_id?: string | null;
    enabled: boolean;
  }>;
  content_hash: string;
}

export type QualityIssueAction = 'confirm' | 'retry';

export type RenderJobStatus =
  | 'queued'
  | 'running'
  | 'pause_requested'
  | 'paused'
  | 'cancel_requested'
  | 'succeeded'
  | 'failed'
  | 'cancelled';

export type RenderJobAction = 'pause' | 'resume' | 'cancel' | 'retry';

export interface RenderJob {
  id: string;
  project_id: string;
  job_type: string;
  status: RenderJobStatus;
  progress: number;
  attempts: number;
  max_attempts: number;
  stage: string;
  message: string;
  error: string | null;
  error_code: string | null;
  revision: number;
  created_at: string;
  updated_at: string;
  heartbeat_at: string | null;
  started_at: string | null;
  finished_at: string | null;
  result: VideoExportResult | null;
}

export interface RenderJobSubmission {
  job: RenderJob;
  created: boolean;
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

export interface SubtitleStyleTemplateRecord {
  id: string;
  name: string;
  font_family: string;
  font_size: number;
  color: string;
  outline_color: string;
  outline_width: number;
  background_color: string;
  background_opacity: number;
  position: 'top' | 'center' | 'bottom';
  animation: 'none' | 'fade' | 'word_highlight';
  highlight_color: string;
}

export interface SubtitleWorkbenchCueRecord {
  id: string;
  start_ms: number;
  end_ms: number;
  text: string;
  translation: string | null;
  words: Array<{ text: string; start_ms: number; end_ms: number; highlighted: boolean }>;
  style_template_id: string | null;
  style_override: SubtitleStyleTemplateRecord | null;
  line_breaks: number[];
  source_word_indexes: number[];
  locked: boolean;
}

export interface SubtitleWorkbenchTrackRecord {
  id: string;
  language: string;
  label: string;
  primary: boolean;
  visible: boolean;
  cues: SubtitleWorkbenchCueRecord[];
}

export interface SubtitleWorkbenchRecord {
  version: number;
  revision: number;
  duration_ms: number;
  render_mode: 'soft' | 'burn_in';
  default_style: SubtitleStyleTemplateRecord;
  templates: SubtitleStyleTemplateRecord[];
  tracks: SubtitleWorkbenchTrackRecord[];
  updated_at: string;
  content_hash: string;
}

export interface ContinuityPlanRecord {
  version: number;
  revision: number;
  project_id: string;
  duration_ms: number;
  transitions: Array<{
    id: string;
    from_page_id: string;
    to_page_id: string;
    kind: 'cut' | 'dissolve' | 'wipe' | 'slide' | 'match';
    duration_ms: number;
    audio_mode: 'cut' | 'j_cut' | 'l_cut';
    audio_offset_ms: number;
    easing: 'linear' | 'ease_in' | 'ease_out' | 'ease_in_out';
    enabled: boolean;
    chapter_boundary: boolean;
  }>;
  overlays: Array<{
    id: string;
    source_ref: string;
    kind: 'image' | 'video' | 'logo' | 'sticker' | 'text';
    start_ms: number;
    duration_ms: number;
    x: number;
    y: number;
    width: number;
    height: number;
    opacity: number;
    crop: 'contain' | 'cover' | 'fill';
    mask: 'none' | 'circle' | 'rounded';
    enter_ms: number;
    exit_ms: number;
    license_asset_id: string | null;
    z_index: number;
  }>;
  chapters: Array<{
    id: string;
    title: string;
    start_ms: number;
    end_ms: number;
    page_ids: string[];
  }>;
  content_hash: string;
}

export interface ExportPresetRecord {
  id: string;
  label: string;
  platform: 'master' | 'youtube' | 'bilibili' | 'douyin' | 'instagram' | 'gif';
  width: number;
  height: number;
  fps: 24 | 25 | 30 | 60;
  video_bitrate: string;
  audio_bitrate: string;
  container: 'mp4' | 'gif';
  video_codec: 'libx264' | 'libx265' | 'gif';
  max_segment_seconds: number | null;
}

export interface ExportPlanRecord {
  plan_id: string;
  project_id: string;
  revision: number;
  created_at: string;
  preset: ExportPresetRecord;
  source_timeline_revision: number | null;
  output_relative_path: string;
  segment_paths: string[];
  ffmpeg_video_filter: string;
  execution_ready: boolean;
  content_hash: string;
}

export interface BatchProductionRecord {
  version: number;
  revision: number;
  batch_id: string;
  project_id: string;
  created_at: string;
  status: 'queued' | 'running' | 'succeeded' | 'partial' | 'failed' | 'cancelled';
  night_queue: boolean;
  resource_limits: {
    max_parallel: number;
    cpu_cores: number;
    memory_mb: number;
    gpu_slots: number;
    per_job_memory_mb: number;
  };
  items: Array<{
    item_id: string;
    preset_id: string;
    page_id: string | null;
    priority: number;
    dependencies: string[];
    resource_cpu: number;
    resource_memory_mb: number;
    resource_gpu: number;
    status: 'queued' | 'dispatched' | 'running' | 'succeeded' | 'failed' | 'cancelled';
    job_id: string | null;
    attempts: number;
    error: string | null;
  }>;
  content_hash: string;
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
  getSubtitleWorkbench: (id: string) =>
    request<SubtitleWorkbenchRecord>(`/api/projects/${id}/subtitle-workbench`),
  createSubtitleWorkbench: (id: string) =>
    request<SubtitleWorkbenchRecord>(`/api/projects/${id}/subtitle-workbench`, { method: 'POST' }),
  subtitleWorkbenchCommand: (id: string, command: Record<string, unknown>) =>
    request<SubtitleWorkbenchRecord>(`/api/projects/${id}/subtitle-workbench/commands`, {
      method: 'POST',
      body: JSON.stringify(command),
    }),
  subtitleWorkbenchTranslate: (id: string, payload: Record<string, unknown>) =>
    request<{ document: SubtitleWorkbenchRecord; translated_cue_count: number }>(
      `/api/projects/${id}/subtitle-workbench/translate`,
      { method: 'POST', body: JSON.stringify(payload) },
    ),
  getContinuityPlan: (id: string) =>
    request<ContinuityPlanRecord>(`/api/projects/${id}/continuity`),
  continuityCommand: (id: string, command: Record<string, unknown>) =>
    request<ContinuityPlanRecord>(`/api/projects/${id}/continuity/commands`, {
      method: 'POST',
      body: JSON.stringify(command),
    }),
  exportPresets: (id: string) =>
    request<ExportPresetRecord[]>(`/api/projects/${id}/exports/presets`),
  exportPlans: (id: string) => request<ExportPlanRecord[]>(`/api/projects/${id}/exports/plans`),
  createExportPlan: (id: string, payload: Record<string, unknown>) =>
    request<ExportPlanRecord>(`/api/projects/${id}/exports/plans`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  listBatchProductions: (id: string) =>
    request<BatchProductionRecord[]>(`/api/projects/${id}/batch-productions`),
  createBatchProduction: (id: string, payload: Record<string, unknown>) =>
    request<BatchProductionRecord>(`/api/projects/${id}/batch-productions`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  dispatchBatchProduction: (id: string, batchId: string, payload?: Record<string, unknown>) =>
    request<{ batch: BatchProductionRecord; dispatched_item_ids: string[] }>(
      `/api/projects/${id}/batch-productions/${batchId}/dispatch`,
      { method: 'POST', body: JSON.stringify(payload ?? {}) },
    ),
  syncBatchProduction: (id: string, batchId: string) =>
    request<BatchProductionRecord>(`/api/projects/${id}/batch-productions/${batchId}/sync`, {
      method: 'POST',
    }),
  rerunBatchFailures: (id: string, batchId: string, itemIds: string[]) =>
    request<BatchProductionRecord>(
      `/api/projects/${id}/batch-productions/${batchId}/rerun-failed`,
      {
        method: 'POST',
        body: JSON.stringify({ item_ids: itemIds }),
      },
    ),
  audioGate: (id: string) => request<AudioGateResult>(`/api/projects/${id}/audio/gate`),
  videoPreflight: (id: string, settings?: { reduced_motion: boolean }) =>
    request<VideoPreflight>(`/api/projects/${id}/video/preflight`, {
      method: 'POST',
      ...(settings ? { body: JSON.stringify(settings) } : {}),
    }),
  videoPreview: (id: string) => request<VideoPreflight>(`/api/projects/${id}/video/preview`),
  videoRender: (id: string) =>
    request<VideoExportResult>(`/api/projects/${id}/video/render`, { method: 'POST' }),
  createRenderJob: (id: string) =>
    request<RenderJobSubmission>(`/api/projects/${id}/video/render-jobs`, { method: 'POST' }),
  getCurrentRenderJob: (id: string) =>
    request<{ job: RenderJob } | null>(`/api/projects/${id}/video/render-jobs/current`),
  createQualityJob: (id: string, input: { video_path: string; expected_duration_ms: number }) =>
    request<QualityJobRecord>(`/api/projects/${id}/quality/jobs`, {
      method: 'POST',
      body: JSON.stringify(input),
    }),
  latestQualityJob: (id: string) => request<QualityJobRecord>(`/api/projects/${id}/quality/latest`),
  retryQualityJob: (id: string, jobId: string) =>
    request<QualityJobRecord>(`/api/projects/${id}/quality/jobs/${jobId}/retry`, {
      method: 'POST',
    }),
  qualityIssueAction: (id: string, jobId: string, issueId: string, action: QualityIssueAction) =>
    request<QualityJobRecord>(
      `/api/projects/${id}/quality/jobs/${jobId}/issues/${issueId}/actions`,
      { method: 'POST', body: JSON.stringify({ action }) },
    ),
  getTimeline: (id: string) => request<ProductionTimelineRecord>(`/api/projects/${id}/timeline`),
  timelineCommand: (id: string, command: Record<string, unknown>) =>
    request<ProductionTimelineRecord>(`/api/projects/${id}/timeline/commands`, {
      method: 'POST',
      body: JSON.stringify(command),
    }),
  timelineCommandBatch: (id: string, batch: Record<string, unknown>) =>
    request<ProductionTimelineRecord>(`/api/projects/${id}/timeline/commands:batch`, {
      method: 'POST',
      body: JSON.stringify(batch),
    }),
  compileTimeline: (id: string) =>
    request<RenderGraphRecord>(`/api/projects/${id}/timeline/compile`, { method: 'POST' }),
  compileTimelineV2: (id: string) =>
    request<RenderGraphV2Record>(`/api/projects/${id}/timeline/compile-v2`, { method: 'POST' }),
  getRenderGraphV2: (id: string) =>
    request<RenderGraphV2Record>(`/api/projects/${id}/render-graph-v2`),
  listAssets: (id: string, kind?: string) =>
    request<AssetRecord[]>(
      `/api/projects/${id}/assets${kind ? `?kind=${encodeURIComponent(kind)}` : ''}`,
    ),
  getMaterialCollection: (id: string) =>
    request<MaterialCollectionRecord>(`/api/projects/${id}/material-collections`),
  createMaterialCollection: (id: string, collection: Record<string, unknown>) =>
    request<MaterialCollectionRecord>(`/api/projects/${id}/material-collections`, {
      method: 'POST',
      body: JSON.stringify(collection),
    }),
  materialCommand: (id: string, command: Record<string, unknown>) =>
    request<MaterialCollectionRecord>(`/api/projects/${id}/material-collections/commands`, {
      method: 'POST',
      body: JSON.stringify(command),
    }),
  materialSyncPreview: (id: string, timelineRevision?: number) =>
    request<{
      collection_revision: number;
      timeline_revision: number | null;
      added_page_ids: string[];
      disabled_page_ids: string[];
      warnings: string[];
    }>(
      `/api/projects/${id}/material-collections/sync-preview${timelineRevision ? `?timeline_revision=${timelineRevision}` : ''}`,
    ),
  getRenderJob: (projectId: string, jobId: string) =>
    request<{ job: RenderJob }>(`/api/projects/${projectId}/video/render-jobs/${jobId}`),
  actOnRenderJob: (projectId: string, jobId: string, action: RenderJobAction) =>
    request<RenderJobSubmission>(`/api/projects/${projectId}/video/render-jobs/${jobId}/actions`, {
      method: 'POST',
      body: JSON.stringify({ action }),
    }),
  effectWorkspace: (id: string) => request<EffectWorkspace>(`/api/projects/${id}/effects`),
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
