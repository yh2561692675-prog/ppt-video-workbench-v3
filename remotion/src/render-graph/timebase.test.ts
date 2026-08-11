import { describe, expect, it } from 'vitest';

import fixture from '../../../tests/fixtures/rendergraph-v2/timebase.json';

import { durationToFrames, usRangeToFrames, usToFrameCeil, usToFrameFloor } from './timebase';

describe('RenderGraph timebase', () => {
  it('uses floor-start and half-open ceil-end boundaries', () => {
    expect(usToFrameFloor(33_333, 30)).toBe(0);
    expect(usToFrameCeil(33_334, 30)).toBe(2);
    expect(usRangeToFrames(33_333, 66_667, 30)).toEqual({ start: 0, end: 2 });
    expect(durationToFrames(0, 30)).toBe(1);
  });

  it('matches the shared fps matrix fixture', () => {
    for (const testCase of fixture.fps_matrix) {
      expect(durationToFrames(testCase.duration_us, testCase.fps)).toBe(testCase.duration_frames);
      expect(usRangeToFrames(testCase.start_us, testCase.end_us, testCase.fps)).toEqual({
        start: testCase.start_frame,
        end: testCase.end_frame_exclusive,
      });
    }
  });
});
