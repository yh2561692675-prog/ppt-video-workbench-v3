export type SubtitleCue = {
  id: string;
  page_id: string;
  page_order: number;
  start_ms: number;
  end_ms: number;
  text: string;
  source_word_indexes: number[];
};

export type VideoPageProps = {
  page_id: string;
  page_order: number;
  title: string;
  image_path: string;
  audio_path: string;
  start_ms: number;
  end_ms: number;
  subtitle_cue_ids: string[];
  effect_plan?: import('../types').EffectPlanV2 | null;
  effect_plan_revision?: number | null;
  effect_plan_hash?: string | null;
};

export type SubtitlePlacement = {
  page_id: string;
  position: 'top' | 'middle' | 'bottom' | 'fallback-panel';
  rect: { x: number; y: number; width: number; height: number };
  panel: boolean;
  reason: string | null;
};

export type PresenterTimeline = {
  schema_version: '1.0';
  revision: number;
  source_id: string;
  source_version: string;
  duration_ms: number;
  anchors: Array<{
    page_id: string;
    start_ms: number;
    end_ms: number;
    sentence_ids: string[];
    confidence: number;
    status: 'auto' | 'review' | 'blocked' | 'confirmed';
    manual_lock: boolean;
    source_revision: string | null;
  }>;
  segments: Array<{
    start_ms: number;
    end_ms: number;
    layout:
      | 'top_left'
      | 'top_right'
      | 'bottom_left'
      | 'bottom_right'
      | 'center'
      | 'split'
      | 'hidden';
    width_ratio: number;
    manual_lock: boolean;
    source_revision: string | null;
  }>;
  unassigned_ranges: Array<{ start_ms: number; end_ms: number; reason: string }>;
  timeline_hash: string | null;
  generated_at: string | null;
};

export type ProjectVideoProps = {
  schema_version: 1 | 2;
  project_id: string;
  width: number;
  height: number;
  fps: number;
  duration_ms: number;
  template_version: string;
  reduced_motion: boolean;
  pages: VideoPageProps[];
  subtitles: SubtitleCue[];
  subtitle_placements: SubtitlePlacement[];
  catalog_version?: string | null;
  presenter_timeline?: PresenterTimeline | null;
  presenter_source_path?: string | null;
  timeline_revision?: number | null;
  timeline_hash?: string | null;
};

export function msToFrames(milliseconds: number, fps: number): number {
  if (milliseconds < 0 || fps <= 0) {
    throw new Error('毫秒数和 FPS 必须为正数或零');
  }
  return Math.floor((milliseconds * fps + 500) / 1000);
}

export function parseProjectVideoProps(input: unknown): ProjectVideoProps {
  if (!input || typeof input !== 'object' || Array.isArray(input)) {
    throw new Error('视频 Props 必须是对象');
  }
  const record = input as Record<string, unknown>;
  const allowed = new Set([
    'schema_version',
    'project_id',
    'width',
    'height',
    'fps',
    'duration_ms',
    'template_version',
    'reduced_motion',
    'pages',
    'subtitles',
    'subtitle_placements',
    'catalog_version',
    'presenter_timeline',
    'presenter_source_path',
    'timeline_revision',
    'timeline_hash',
  ]);
  for (const key of Object.keys(record)) {
    if (!allowed.has(key)) throw new Error(`未知字段: ${key}`);
  }
  if (!isQualifiedCanvas(record.width, record.height)) {
    throw new Error('视频画布必须是已验证的 720p/1080p 规格或 4K 16:9');
  }
  if (!isQualifiedFps(record.fps)) throw new Error('视频 FPS 必须是 24、25、30 或 60');
  if (!Array.isArray(record.pages) || record.pages.length === 0) {
    throw new Error('视频 Props 至少需要一个页面');
  }
  if (!Array.isArray(record.subtitle_placements)) {
    throw new Error('视频 Props 缺少字幕避让结果');
  }
  const pages = record.pages as Array<Record<string, unknown>>;
  for (let index = 0; index < pages.length; index += 1) {
    if (pages[index]?.page_order !== index + 1) throw new Error('页面顺序必须从 1 连续递增');
  }
  if (record.schema_version === 2) {
    for (const page of pages) {
      if (!page.effect_plan || typeof page.effect_plan_hash !== 'string') {
        throw new Error('V2 视频 Props 缺少页面特效计划');
      }
    }
  }
  if (record.presenter_timeline) {
    const timeline = record.presenter_timeline as PresenterTimeline;
    if (record.timeline_revision !== timeline.revision) {
      throw new Error('presenter timeline revision mismatch');
    }
    if (record.timeline_hash !== timeline.timeline_hash) {
      throw new Error('presenter timeline hash mismatch');
    }
    if (typeof record.presenter_source_path !== 'string' || !record.presenter_source_path) {
      throw new Error('presenter timeline requires source path');
    }
  }
  return input as ProjectVideoProps;
}

const QUALIFIED_CANVASES = new Set([
  '1280x720',
  '1920x1080',
  '720x1280',
  '1080x1920',
  '720x720',
  '1080x1080',
  '3840x2160',
]);

function isQualifiedCanvas(width: unknown, height: unknown): boolean {
  return (
    typeof width === 'number' &&
    Number.isInteger(width) &&
    typeof height === 'number' &&
    Number.isInteger(height) &&
    QUALIFIED_CANVASES.has(`${width}x${height}`)
  );
}

function isQualifiedFps(fps: unknown): fps is 24 | 25 | 30 | 60 {
  return fps === 24 || fps === 25 || fps === 30 || fps === 60;
}
