export function GaugeAndRatio({ value, label }: { value: number; label: string }) {
  const normalized = Math.min(1, Math.max(0, value));
  const percent = Math.round(normalized * 100);
  const radius = 42;
  const circumference = 2 * Math.PI * radius;
  const dashOffset = circumference * (1 - normalized);
  return (
    <div className="gauge-ratio" aria-label={`${label} ${percent}%`}>
      <svg viewBox="0 0 100 100" role="img" aria-hidden="true">
        <circle cx="50" cy="50" r={radius} fill="none" stroke="#173449" strokeWidth="8" />
        <circle
          cx="50"
          cy="50"
          r={radius}
          fill="none"
          stroke="#47e6d0"
          strokeWidth="8"
          strokeDasharray={circumference}
          strokeDashoffset={dashOffset}
          transform="rotate(-90 50 50)"
        />
      </svg>
      <span className="gauge-ratio__value">{percent}%</span>
      <span className="gauge-ratio__label">{label}</span>
    </div>
  );
}
