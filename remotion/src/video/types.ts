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

export type ProjectVideoProps = {
  schema_version: 1 | 2;
  project_id: string;
  width: 1920 | 1080;
  height: 1080 | 1920;
  fps: 30;
  duration_ms: number;
  template_version: string;
  reduced_motion: boolean;
  pages: VideoPageProps[];
  subtitles: SubtitleCue[];
  subtitle_placements: SubtitlePlacement[];
  catalog_version?: string | null;
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
  ]);
  for (const key of Object.keys(record)) {
    if (!allowed.has(key)) throw new Error(`未知字段: ${key}`);
  }
  if (record.width !== 1920 && record.width !== 1080) throw new Error('视频画布宽度必须为 1920 或 1080');
  if (record.height !== 1080 && record.height !== 1920) throw new Error('视频画布高度必须为 1080 或 1920');
  if (record.fps !== 30) throw new Error('视频 FPS 必须为 30');
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
  return input as ProjectVideoProps;
}
