import type { EffectTemplateProps } from '../registry';

export function ProgressiveReveal({ plan, currentFrame }: EffectTemplateProps) {
  const nowMs = (currentFrame * 1000) / 30;
  const visible = plan.cues.filter((cue) => cue.start_ms <= nowMs);
  return (
    <div className="effect-progressive-reveal" data-template="ProgressiveReveal">
      {visible.map((cue) => (
        <div key={cue.id} className="effect-progressive-reveal__cue" data-cue-id={cue.id}>
          {cue.text}
        </div>
      ))}
    </div>
  );
}
