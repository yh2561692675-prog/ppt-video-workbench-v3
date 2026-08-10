import type { EffectPlanV2 } from '../types';

const ALLOWED_FIELDS = new Set([
  'schema_version',
  'page_id',
  'page_type',
  'duration_ms',
  'aspect_ratio',
  'rhythm_profile',
  'background_preset',
  'template',
  'template_payload',
  'cues',
  'effects',
  'camera',
  'transition',
  'presenter_cues',
  'manual_lock',
  'fallback',
  'source_hashes',
  'migration_version',
  'legacy_payload_hash',
]);

export function parseEffectPlan(input: unknown): EffectPlanV2 {
  if (!input || typeof input !== 'object' || Array.isArray(input)) {
    throw new Error('EffectPlan must be an object');
  }
  const record = input as Record<string, unknown>;
  for (const key of Object.keys(record)) {
    if (!ALLOWED_FIELDS.has(key)) throw new Error(`Unknown EffectPlan field: ${key}`);
  }
  if (record.schema_version !== '2.0') throw new Error('EffectPlan schema_version must be 2.0');
  if (typeof record.page_id !== 'string' || record.page_id.length === 0)
    throw new Error('EffectPlan page_id is required');
  if (typeof record.page_type !== 'string' || record.page_type.length === 0)
    throw new Error('EffectPlan page_type is required');
  if (typeof record.duration_ms !== 'number' || record.duration_ms <= 0)
    throw new Error('EffectPlan duration_ms must be positive');
  if (record.aspect_ratio !== '16:9' && record.aspect_ratio !== '9:16')
    throw new Error('EffectPlan aspect_ratio is invalid');
  if (record.template !== undefined && typeof record.template !== 'string')
    throw new Error('EffectPlan template is invalid');
  if (
    !Array.isArray(record.cues) ||
    !Array.isArray(record.effects) ||
    !Array.isArray(record.presenter_cues)
  ) {
    throw new Error('EffectPlan timeline arrays are required');
  }
  return input as EffectPlanV2;
}
