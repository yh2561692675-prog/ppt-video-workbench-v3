/* eslint-disable react-refresh/only-export-components */

export function riskPulseFrames(durationFrames: number): number[] {
  if (durationFrames <= 0) return [];
  return [Math.floor(durationFrames * 0.35)];
}

export function RiskAlert({ title, reason }: { title: string; reason: string }) {
  return (
    <div className="risk-alert" data-pulse="single">
      <div className="risk-alert__title">{title}</div>
      <div className="risk-alert__reason">{reason}</div>
    </div>
  );
}
