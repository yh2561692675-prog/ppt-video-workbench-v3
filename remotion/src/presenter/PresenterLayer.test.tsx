import { describe, expect, it } from 'vitest';

import type { PresenterTimeline } from '../video/types';
import { presenterBoxStyle } from './presenterStyle';
import { getPresenterRenderState } from './presenterRenderState';

const timeline: PresenterTimeline = {
  schema_version: '1.0',
  revision: 1,
  source_id: '00000000-0000-0000-0000-000000000001',
  source_version: 'a'.repeat(64),
  duration_ms: 20_000,
  anchors: [],
  segments: [
    {
      start_ms: 0,
      end_ms: 5_000,
      layout: 'top_right',
      width_ratio: 0.22,
      manual_lock: false,
      source_revision: null,
    },
    {
      start_ms: 5_000,
      end_ms: 20_000,
      layout: 'hidden',
      width_ratio: 0,
      manual_lock: false,
      source_revision: null,
    },
  ],
  unassigned_ranges: [],
  timeline_hash: 'b'.repeat(64),
  generated_at: null,
};

describe('PresenterLayer', () => {
  it('keeps audio active while the presenter window is hidden', () => {
    const state = getPresenterRenderState(300, 30, timeline);
    expect(state.videoVisible).toBe(false);
    expect(state.masterAudioEnabled).toBe(true);
  });

  it('uses deterministic canvas-relative geometry', () => {
    const style = presenterBoxStyle(timeline.segments[0], 1920, 1080);
    expect(style.width).toBe(422.4);
    expect(style.right).toBe(76.8);
    expect(style.top).toBe(43.2);
  });
});
