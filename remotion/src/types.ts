export type AspectRatio = '16:9' | '9:16';
export type RhythmProfile = 'steady' | 'standard' | 'compact' | 'enhanced';
export type BackgroundPreset =
  | 'tech_blue'
  | 'risk_red'
  | 'warm_gold'
  | 'paper_grid'
  | 'regional_teal';

export type EffectCue = {
  id: string;
  start_ms: number;
  end_ms: number;
  kind: string;
  text: string;
};

export type EffectEvent = {
  type: string;
  start_ms: number;
  end_ms: number;
  target: string | null;
  intensity: number;
};

export type EffectPlanV2 = {
  schema_version: '2.0';
  page_id: string;
  page_type: string;
  duration_ms: number;
  aspect_ratio: AspectRatio;
  rhythm_profile: RhythmProfile;
  background_preset: BackgroundPreset;
  template?: EffectTemplateName;
  template_payload?: Record<string, unknown>;
  cues: EffectCue[];
  effects: EffectEvent[];
  camera: {
    mode: 'static' | 'push' | 'pan' | 'spotlight';
    scale_start: number;
    scale_end: number;
    focus_x: number;
    focus_y: number;
  };
  transition: { type: 'cut' | 'crossfade' | 'mask'; duration_ms: number };
  presenter_cues: Array<{ start_ms: number; end_ms: number; position: string; reason: string }>;
  manual_lock: boolean;
  fallback: { template: 'SafeSlide' | 'FocusSpotlight'; reason: string | null };
  source_hashes: Record<string, string>;
  migration_version: string | null;
  legacy_payload_hash: string | null;
};

export type EffectTemplateName =
  | 'ProgressiveReveal'
  | 'ChapterCurtain'
  | 'StatCounter'
  | 'ChartNarration'
  | 'CompareMode'
  | 'FocusSpotlight'
  | 'CardStack'
  | 'GaugeAndRatio'
  | 'PathBuilder'
  | 'TagMatrix'
  | 'RiskAlert'
  | 'MapHighlight'
  | 'SafeSlide';
