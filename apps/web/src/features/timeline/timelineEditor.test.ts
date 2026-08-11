import { describe, expect, it } from 'vitest';

import { createMovePreview, snapTimeUs, timeFromPointer, updateSelection } from './timelineEditor';

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
});
