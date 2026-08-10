import type { CSSProperties } from 'react';

import type { EffectTemplateProps } from '../registry';

export function SafeSlide({ plan, currentFrame }: EffectTemplateProps) {
  const progress = clamp(
    currentFrame / Math.max(1, Math.round((plan.duration_ms / 1000) * 30)),
    0,
    1,
  );
  const style: CSSProperties = {
    position: 'absolute',
    inset: 0,
    opacity: 0.72 + progress * 0.28,
    transform: `scale(${(1 + progress * 0.03).toFixed(4)})`,
    transformOrigin: 'center center',
    background: 'linear-gradient(135deg, #07111f 0%, #0b2031 55%, #07111f 100%)',
  };
  return <div className="effect-safe-slide" data-template="SafeSlide" style={style} />;
}

function clamp(value: number, minimum: number, maximum: number): number {
  return Math.min(maximum, Math.max(minimum, value));
}
