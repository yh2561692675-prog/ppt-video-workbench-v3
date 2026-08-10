/* eslint-disable react-refresh/only-export-components */

export type CounterSpec = {
  start: number;
  end: number;
  durationFrames: number;
  format: 'integer' | 'percent';
};

export function counterValue(spec: CounterSpec, currentFrame: number): number {
  if (currentFrame >= spec.durationFrames - 1) return spec.end;
  if (currentFrame <= 0) return spec.start;
  const progress = Math.min(1, Math.max(0, currentFrame / Math.max(1, spec.durationFrames - 1)));
  return Math.round(spec.start + (spec.end - spec.start) * progress);
}

export function StatCounter({ spec, currentFrame }: { spec: CounterSpec; currentFrame: number }) {
  const value = counterValue(spec, currentFrame);
  const label = spec.format === 'percent' ? `${value}%` : value.toLocaleString('en-US');
  return (
    <div className="stat-counter" data-value={value}>
      {label}
    </div>
  );
}
