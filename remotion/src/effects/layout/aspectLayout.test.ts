import { describe, expect, it } from 'vitest';

import { resolveLayout } from './aspectLayout';

describe('aspect layout', () => {
  it('uses stacked regions for a vertical comparison page', () => {
    const layout = resolveLayout('CompareMode', '9:16', {
      captionSafeArea: { x: 0.1, y: 0.78, width: 0.8, height: 0.12 },
      presenterRect: null,
    });
    expect(layout.direction).toBe('vertical');
    expect(layout.fontScale).toBeGreaterThanOrEqual(0.85);
  });

  it('keeps presenter and captions from occupying the same region', () => {
    const layout = resolveLayout('MapHighlight', '9:16', {
      captionSafeArea: { x: 0.1, y: 0.75, width: 0.8, height: 0.15 },
      presenterRect: { x: 0.05, y: 0.7, width: 0.35, height: 0.25 },
    });
    expect(layout.presenterRect).not.toEqual(layout.captionSafeArea);
    expect(layout.collisionResolved).toBe(true);
  });
});
