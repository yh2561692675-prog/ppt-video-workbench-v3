type ChartPoint = { label: string; value: number };
type CuePoint = { index: number; text: string };

export function ChartNarration({
  series,
  cuePoints,
  annotation,
}: {
  series: ChartPoint[];
  cuePoints: CuePoint[];
  annotation: string;
}) {
  if (series.length === 0 || series.some((point) => !Number.isFinite(point.value))) {
    return <div className="chart-static-fallback">{annotation}</div>;
  }
  return (
    <div className="chart-narration">
      <div className="chart-baseline" />
      <div className="chart-series">
        {series.map((point) => (
          <span key={point.label}>
            {point.label}:{point.value}
          </span>
        ))}
      </div>
      <div className="chart-key-point">
        {cuePoints.map((point) => (
          <span key={`${point.index}-${point.text}`}>{point.text}</span>
        ))}
      </div>
      <div className="chart-annotation">{annotation}</div>
      <div className="chart-conclusion">{annotation}</div>
    </div>
  );
}
