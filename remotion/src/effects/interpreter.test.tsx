import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import { EffectInterpreter, interpret } from './interpreter';

const basePlan = {
  schema_version: '2.0' as const,
  page_id: 'page-1',
  page_type: 'content',
  duration_ms: 5000,
  aspect_ratio: '16:9' as const,
  rhythm_profile: 'steady' as const,
  background_preset: 'tech_blue' as const,
  cues: [],
  effects: [],
  camera: { mode: 'static' as const, scale_start: 1, scale_end: 1, focus_x: 0.5, focus_y: 0.5 },
  transition: { type: 'crossfade' as const, duration_ms: 400 },
  presenter_cues: [],
  manual_lock: false,
  fallback: { template: 'SafeSlide' as const, reason: null },
  source_hashes: {},
  migration_version: null,
  legacy_payload_hash: null,
};

describe('EffectInterpreter', () => {
  it('falls back for an unknown effect without throwing', () => {
    const output = interpret(
      {
        ...basePlan,
        effects: [
          { type: 'UnknownTemplate', start_ms: 0, end_ms: 500, target: null, intensity: 1 },
        ],
      },
      30,
    );

    expect(output.template).toBe('SafeSlide');
    expect(output.issueCode).toBe('EFFECT_TEMPLATE_UNKNOWN');
  });

  it('renders the registered template deterministically', () => {
    const first = renderToStaticMarkup(<EffectInterpreter plan={basePlan} currentFrame={30} />);
    const second = renderToStaticMarkup(<EffectInterpreter plan={basePlan} currentFrame={30} />);

    expect(first).toBe(second);
    expect(first).toContain('effect-safe-slide');
  });

  it('uses SafeSlide when a cue or event is outside the page timeline', () => {
    const output = interpret(
      {
        ...basePlan,
        effects: [
          { type: 'FocusSpotlight', start_ms: 0, end_ms: 9000, target: null, intensity: 1 },
        ],
      },
      30,
    );

    expect(output.template).toBe('SafeSlide');
    expect(output.issueCode).toBe('EFFECT_TIMELINE_INVALID');
  });
});
