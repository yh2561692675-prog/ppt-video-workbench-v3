import type { EffectTemplateProps } from '../registry';

export function FocusSpotlight({ plan, currentFrame }: EffectTemplateProps) {
  const active = plan.effects.find((effect) => {
    const nowMs = (currentFrame * 1000) / 30;
    return effect.start_ms <= nowMs && nowMs < effect.end_ms;
  });
  const opacity = active ? 0.18 : 0.42;
  return (
    <div
      className="effect-focus-spotlight"
      data-template="FocusSpotlight"
      data-target={active?.target ?? 'current-content'}
      style={{ position: 'absolute', inset: 0, background: `rgb(0 0 0 / ${opacity})` }}
    />
  );
}
