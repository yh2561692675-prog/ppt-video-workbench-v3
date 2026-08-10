import { describe, expect, it } from 'vitest';

import { msToFrames, parseProjectVideoProps } from './types';

const fixture = {
  schema_version: 1,
  project_id: '00000000-0000-0000-0000-000000000001',
  width: 1920,
  height: 1080,
  fps: 30,
  duration_ms: 2000,
  template_version: 'tech-board-v1',
  reduced_motion: false,
  pages: [
    {
      page_id: '00000000-0000-0000-0000-000000000002',
      page_order: 1,
      title: '第一页',
      image_path: '02_页面预览/page-0001.png',
      audio_path: '05_音频/page-0001.wav',
      start_ms: 0,
      end_ms: 2000,
      subtitle_cue_ids: [],
    },
  ],
  subtitles: [],
  subtitle_placements: [],
};

describe('ProjectVideoProps', () => {
  it('keeps the fixed canvas and deterministic frame conversion', () => {
    const props = parseProjectVideoProps(fixture);
    expect([props.width, props.height, props.fps]).toEqual([1920, 1080, 30]);
    expect(msToFrames(2000, props.fps)).toBe(60);
    expect(msToFrames(50, props.fps)).toBe(2);
  });

  it('rejects a non-16:9 canvas and unknown fields', () => {
    expect(() => parseProjectVideoProps({ ...fixture, width: 1280 })).toThrow(/1920/);
    expect(() => parseProjectVideoProps({ ...fixture, unknown: true })).toThrow(/unknown|未知/i);
  });
});
