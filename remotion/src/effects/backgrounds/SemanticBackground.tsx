import type { CSSProperties } from 'react';

type BackgroundPreset = 'tech_blue' | 'risk_red' | 'warm_gold' | 'paper_grid' | 'regional_teal';

const colors: Record<BackgroundPreset, [string, string]> = {
  tech_blue: ['#07111f', '#0b2031'],
  risk_red: ['#1d0b12', '#3a1218'],
  warm_gold: ['#1f1508', '#3b2910'],
  paper_grid: ['#f4f7fa', '#e7edf2'],
  regional_teal: ['#071b1d', '#0d3a3a'],
};

export function SemanticBackground({
  preset,
  foregroundActive,
  reducedMotion = false,
}: {
  preset: BackgroundPreset;
  foregroundActive: boolean;
  reducedMotion?: boolean;
}) {
  const [start, end] = colors[preset];
  const brightness = foregroundActive ? 0.72 : 1;
  const style: CSSProperties = {
    position: 'absolute',
    inset: 0,
    background: `linear-gradient(135deg, ${start} 0%, ${end} 100%)`,
    filter: `brightness(${brightness})`,
    opacity: reducedMotion ? 1 : 0.98,
  };
  return (
    <div
      className="semantic-background"
      data-background-brightness={brightness}
      data-preset={preset}
      style={style}
    />
  );
}
