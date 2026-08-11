import { describe, expect, it } from 'vitest';

import {
  createMovePreview,
  requestMatchesRevision,
  snapTimeUs,
  timeFromPointer,
  timeToPixels,
  updateSelection,
  visibleClips,
  visibleTimeRange,
  waveformLevelForViewport,
  zoomAroundAnchor,
} from './timelineEditor';

describe('timeline editor primitives', () => {
  it('converts pointer positions to integer microseconds', () => {
    expect(timeFromPointer(200, 100, 100)).toBe(1_000_000);
  });

  it('snaps by the nearest point using the current zoom threshold', () => {
    expect(snapTimeUs(1_020_000, [{ timeUs: 1_000_000, kind: 'page', id: 'page-1' }], 100)).toBe(
      1_000_000,
    );
    expect(snapTimeUs(1_200_000, [{ timeUs: 1_000_000, kind: 'page', id: 'page-1' }], 100)).toBe(
      1_200_000,
    );
  });

  it('supports additive selection and deterministic move previews', () => {
    const first = updateSelection({ clipIds: [], anchorClipId: null }, 'clip-a');
    const second = updateSelection(first, 'clip-b', { additive: true });
    expect(second.clipIds).toEqual(['clip-a', 'clip-b']);
    expect(
      createMovePreview(
        { id: 'clip-b', trackId: 'track-1', startUs: 0, durationUs: 500_000 },
        200,
        100,
        100,
        [{ timeUs: 1_000_000, kind: 'marker', id: 'marker-1' }],
      ).startUs,
    ).toBe(1_000_000);
  });

  it('keeps the zoom anchor stable and virtualizes a large timeline', () => {
    expect(timeToPixels(2_000_000, 100)).toBe(200);
    expect(zoomAroundAnchor(100, 200, 500, 250)).toBe(1250);
    const range = visibleTimeRange(1000, 500, 100, 0);
    expect(range).toEqual({ startUs: 10_000_000, endUs: 15_000_000 });
    const clips = Array.from({ length: 500 }, (_, index) => ({
      id: `${index}`,
      start_us: index * 1_000_000,
      duration_us: 500_000,
    }));
    expect(visibleClips(clips, range)).toHaveLength(5);
  });

  it('selects waveform detail and rejects stale async responses', () => {
    expect(waveformLevelForViewport(9_000)).toBe(0);
    expect(waveformLevelForViewport(300_000)).toBe(3);
    expect(requestMatchesRevision(4, 5)).toBe(false);
  });
});
