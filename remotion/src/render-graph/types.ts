export type RenderGraphHash = string;

export type GraphCanvas = {
  width: number;
  height: number;
  fps: number;
  fps_num?: number | null;
  fps_den: number;
  duration_us: number;
  background: string;
  pixel_format: string;
  aspect_ratio: string;
};

export type ResolvedAsset = {
  asset_id?: string | null;
  revision?: number | null;
  project_id?: string | null;
  kind: string;
  source_ref: string;
  object_relative_path?: string | null;
  proxy_relative_path?: string | null;
  resolved_path?: string | null;
  mime_type?: string | null;
  content_hash?: RenderGraphHash | null;
  exists: boolean;
  size_bytes?: number | null;
  duration_us?: number | null;
  width?: number | null;
  height?: number | null;
  fps_num?: number | null;
  fps_den?: number | null;
  media_probe?: MediaProbeMetadata | null;
  media_probe_status?: 'not_requested' | 'verified' | 'failed' | 'unavailable';
  media_probe_error?: string | null;
  legacy_snapshot?: boolean;
  alpha_mode: 'none' | 'straight' | 'premultiplied';
  license_status: string;
  license_expires_at?: string | null;
  license_snapshot?: Record<string, unknown> | null;
};

export type MediaProbeMetadata = {
  width?: number | null;
  height?: number | null;
  duration_us?: number | null;
  fps_num?: number | null;
  fps_den?: number | null;
};

export type RenderNodeV2 = {
  id: string;
  clip_id?: string | null;
  track_id?: string | null;
  kind: string;
  start_us: number;
  end_us: number;
  start_frame?: number | null;
  end_frame_exclusive?: number | null;
  track_order?: number | null;
  source_in_us: number;
  source_ref: string;
  asset_id?: string | null;
  asset_revision?: number | null;
  z_index: number;
  blend_mode: string;
  opacity: number;
  cache_key?: RenderGraphHash | null;
  payload: Record<string, unknown>;
  depends_on: string[];
};

export type TransitionEdge = {
  id: string;
  from_node_id: string;
  to_node_id: string;
  kind: 'cut' | 'dissolve' | 'wipe' | 'slide' | 'match';
  start_us: number;
  end_us: number;
  duration_us?: number | null;
  easing: 'linear' | 'ease_in' | 'ease_out' | 'ease_in_out';
  audio_mode: 'cut' | 'j_cut' | 'l_cut';
  audio_offset_us: number;
  chapter_boundary: boolean;
  parameters: Record<string, unknown>;
};

export type AudioMixPlan = {
  clips: AudioMixClip[];
  ducking: Array<Record<string, unknown>>;
  loudness_target_lufs: number;
  true_peak_db: number;
  buses?: Array<Record<string, unknown>>;
  automation?: Array<Record<string, unknown>>;
  master?: Record<string, unknown>;
};

export type AudioMixClip = {
  id: string;
  kind: string;
  source_ref: string;
  asset_id?: string | null;
  asset_revision?: number | null;
  timeline_start_us: number;
  timeline_end_us: number;
  source_in_us: number;
  source_duration_us?: number | null;
  bus: string;
  gain_db: number;
  fade_in_us: number;
  fade_out_us: number;
  pan: number;
};

export type SubtitleWord = { text: string; start_us: number; end_us: number };

export type SubtitleCue = {
  id: string;
  language: string;
  label: string;
  start_us: number;
  end_us: number;
  text: string;
  translation?: string | null;
  words: SubtitleWord[];
  line_breaks: number[];
  style: Record<string, unknown>;
  track_id?: string | null;
  primary?: boolean;
  visible?: boolean;
};

export type SubtitleRenderPlan = {
  render_mode: 'burn_in' | 'soft' | 'both' | 'none';
  cues: SubtitleCue[];
  default_style: Record<string, unknown>;
  languages: string[];
  document_revision: number;
  document_hash: RenderGraphHash;
  tracks: Array<Record<string, unknown>>;
};

export type RenderGraphV2 = {
  schema_version: '2.0';
  graph_id: string;
  project_id: string;
  timeline_revision: number;
  timeline_hash: RenderGraphHash;
  compiler_version: string;
  duration_us: number;
  canvas: GraphCanvas;
  nodes: RenderNodeV2[];
  transitions: TransitionEdge[];
  assets: ResolvedAsset[];
  audio: AudioMixPlan;
  audio_mix?: AudioMixPlan;
  subtitles: SubtitleRenderPlan;
  subtitle_plan?: SubtitleRenderPlan;
  source_revisions: Record<string, string>;
  affected_ranges: Array<Record<string, unknown>>;
  graph_hash?: RenderGraphHash;
  content_hash?: RenderGraphHash;
  created_at?: string | null;
};

export type RenderGraphProps = {
  graph: RenderGraphV2;
  executionMode: 'interactive-preview' | 'authoritative-preview' | 'final';
  assetBaseUrl?: string;
};

export { durationToFrames, usToFrames } from './timebase';

const HASH = /^[0-9a-f]{64}$/;
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

export function parseRenderGraph(input: unknown): RenderGraphV2 {
  if (!input || typeof input !== 'object' || Array.isArray(input)) {
    throw new Error('RenderGraph V2 must be an object');
  }
  const value = input as Record<string, unknown>;
  const allowed = new Set([
    'schema_version',
    'graph_id',
    'project_id',
    'timeline_revision',
    'timeline_hash',
    'compiler_version',
    'duration_us',
    'canvas',
    'nodes',
    'transitions',
    'assets',
    'audio',
    'audio_mix',
    'subtitles',
    'subtitle_plan',
    'source_revisions',
    'affected_ranges',
    'graph_hash',
    'content_hash',
    'created_at',
  ]);
  for (const key of Object.keys(value)) {
    if (!allowed.has(key)) throw new Error(`Unknown RenderGraph field: ${key}`);
  }
  if (value.schema_version !== '2.0') throw new Error('RenderGraph schema_version must be 2.0');
  for (const key of ['graph_id', 'project_id']) {
    if (typeof value[key] !== 'string' || !UUID.test(value[key])) {
      throw new Error(`RenderGraph ${key} must be a UUID`);
    }
  }
  for (const key of ['timeline_hash', 'graph_hash', 'content_hash']) {
    if (
      value[key] !== undefined &&
      value[key] !== null &&
      (typeof value[key] !== 'string' || !HASH.test(value[key]))
    ) {
      throw new Error(`RenderGraph ${key} must be a SHA-256 hash`);
    }
  }
  if (value.graph_hash === undefined && value.content_hash === undefined) {
    throw new Error('RenderGraph requires graph_hash or content_hash');
  }
  if (
    !Array.isArray(value.nodes) ||
    !Array.isArray(value.transitions) ||
    !Array.isArray(value.assets)
  ) {
    throw new Error('RenderGraph nodes, transitions and assets are required arrays');
  }
  const canvas = value.canvas as Record<string, unknown> | undefined;
  if (!canvas || typeof canvas.width !== 'number' || typeof canvas.height !== 'number') {
    throw new Error('RenderGraph canvas is required');
  }
  return input as RenderGraphV2;
}
