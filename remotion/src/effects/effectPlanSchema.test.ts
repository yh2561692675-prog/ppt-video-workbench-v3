import { describe, expect, it } from 'vitest';

import { parseEffectPlan } from './effectPlanSchema';

const migratedFixture = {
  schema_version: '2.0',
  page_id: 'page-1',
  page_type: 'content',
  duration_ms: 5000,
  aspect_ratio: '16:9',
  rhythm_profile: 'steady',
  background_preset: 'tech_blue',
  cues: [],
  effects: [{ type: 'fade_in', start_ms: 0, end_ms: 500 }],
  camera: { mode: 'static', scale_start: 1, scale_end: 1 },
  transition: { type: 'crossfade', duration_ms: 400 },
  presenter_cues: [],
  manual_lock: false,
  fallback: { template: 'SafeSlide', reason: null },
  source_hashes: {},
  migration_version: 'v1-to-v2',
  legacy_payload_hash: 'a'.repeat(64),
};

describe('EffectPlan V2 schema', () => {
  it('parses the migrated Python fixture with the same contract', () => {
    const plan = parseEffectPlan(migratedFixture);

    expect(plan.schema_version).toBe('2.0');
    expect(plan.rhythm_profile).toBe('steady');
    expect(plan.effects[0]?.start_ms).toBe(0);
  });

  it('rejects unknown fields', () => {
    expect(() => parseEffectPlan({ ...migratedFixture, unknown: true })).toThrow(
      'Unknown EffectPlan field: unknown',
    );
  });
});
