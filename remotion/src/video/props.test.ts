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
  it('accepts qualified output profiles and keeps deterministic frame conversion', () => {
    const props = parseProjectVideoProps(fixture);
    expect([props.width, props.height, props.fps]).toEqual([1920, 1080, 30]);
    expect(msToFrames(2000, props.fps)).toBe(60);
    expect(msToFrames(50, props.fps)).toBe(2);
  });

  it('accepts landscape, portrait and square output profiles', () => {
    expect(parseProjectVideoProps({ ...fixture, width: 1280, height: 720, fps: 24 }).fps).toBe(24);
    expect(parseProjectVideoProps({ ...fixture, width: 720, height: 1280, fps: 25 }).height).toBe(
      1280,
    );
    expect(parseProjectVideoProps({ ...fixture, width: 1080, height: 1080, fps: 60 }).fps).toBe(60);
  });

  it('rejects an unqualified canvas, frame rate and unknown fields', () => {
    expect(() => parseProjectVideoProps({ ...fixture, width: 1281 })).toThrow(/画布/);
    expect(() => parseProjectVideoProps({ ...fixture, fps: 50 })).toThrow(/FPS/);
    expect(() => parseProjectVideoProps({ ...fixture, unknown: true })).toThrow(/unknown|未知/i);
  });
});
