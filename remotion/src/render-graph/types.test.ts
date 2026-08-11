import { describe, expect, it } from 'vitest';

import { parseRenderGraph } from './types';

const uuid = '11111111-1111-4111-8111-111111111111';
const hash = 'a'.repeat(64);

const fixture = {
  schema_version: '2.0',
  graph_id: uuid,
  project_id: uuid,
  timeline_revision: 1,
  timeline_hash: hash,
  compiler_version: 'test',
  duration_us: 1_000_000,
  canvas: {
    width: 1920,
    height: 1080,
    fps: 30,
    fps_num: 30,
    fps_den: 1,
    duration_us: 1_000_000,
    background: '#000000',
    pixel_format: 'yuv420p',
    aspect_ratio: '16:9',
  },
  nodes: [],
  transitions: [],
  assets: [],
  audio_mix: { clips: [], ducking: [], loudness_target_lufs: -16, true_peak_db: -1 },
  subtitle_plan: {
    render_mode: 'none',
    cues: [],
    default_style: {},
    languages: [],
    document_revision: 1,
    document_hash: hash,
    tracks: [],
  },
  source_revisions: {},
  affected_ranges: [],
  content_hash: hash,
};

describe('RenderGraph V2 contract', () => {
  it('parses canonical aliases', () => {
    expect(parseRenderGraph(fixture).schema_version).toBe('2.0');
  });

  it('rejects unknown fields and invalid hashes', () => {
    expect(() => parseRenderGraph({ ...fixture, unknown: true })).toThrow(
      'Unknown RenderGraph field',
    );
    expect(() => parseRenderGraph({ ...fixture, content_hash: 'bad' })).toThrow('SHA-256');
  });
});
