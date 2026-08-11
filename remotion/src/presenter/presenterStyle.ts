import type { CSSProperties } from 'react';

import type { PresenterTimeline } from '../video/types';

export type PresenterSegment = PresenterTimeline['segments'][number];

export function presenterBoxStyle(
  segment: PresenterSegment,
  canvasWidth: number,
  canvasHeight: number,
): CSSProperties {
  const marginX = canvasWidth * 0.04;
  const marginY = canvasHeight * 0.04;
  const width = canvasWidth * segment.width_ratio;
  const height = width * (9 / 16);
  const positions: Record<Exclude<PresenterSegment['layout'], 'hidden'>, CSSProperties> = {
    top_left: { left: marginX, top: marginY },
    top_right: { right: marginX, top: marginY },
    bottom_left: { left: marginX, bottom: marginY },
    bottom_right: { right: marginX, bottom: marginY },
    center: { left: (canvasWidth - width) / 2, top: (canvasHeight - height) / 2 },
    split: { right: marginX, top: (canvasHeight - height) / 2 },
  };
  if (segment.layout === 'hidden') return { display: 'none' };
  return {
    position: 'absolute',
    width,
    height,
    overflow: 'hidden',
    borderRadius: Math.max(18, width * 0.055),
    border: `${Math.max(2, canvasWidth * 0.0015)}px solid rgba(255,255,255,0.88)`,
    boxShadow: `0 ${Math.round(canvasHeight * 0.018)}px ${Math.round(canvasHeight * 0.045)}px rgba(3, 12, 28, 0.34)`,
    backgroundColor: '#071426',
    zIndex: 4,
    ...positions[segment.layout],
  };
}
