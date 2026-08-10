import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import { counterValue, StatCounter } from './StatCounter';
import { GaugeAndRatio } from './GaugeAndRatio';
import { ChartNarration } from './ChartNarration';

describe('data templates', () => {
  it('always shows the exact final value on the last frame', () => {
    const spec = { start: 0, end: 10427, durationFrames: 42, format: 'integer' as const };
    expect(counterValue(spec, 41)).toBe(10427);
    expect(counterValue(spec, 120)).toBe(10427);
  });

  it('renders a readable ratio ring with its exact label', () => {
    const html = renderToStaticMarkup(<GaugeAndRatio value={0.68} label="升学率" />);
    expect(html).toContain('gauge-ratio');
    expect(html).toContain('68%');
    expect(html).toContain('升学率');
    expect(html).toContain('aria-label="升学率 68%"');
  });

  it('renders chart narration in a fixed educational sequence', () => {
    const html = renderToStaticMarkup(
      <ChartNarration
        series={[
          { label: '2024', value: 10 },
          { label: '2025', value: 16 },
        ]}
        cuePoints={[{ index: 1, text: '增长拐点' }]}
        annotation="结论：持续增长"
      />,
    );
    const order = [
      'chart-baseline',
      'chart-series',
      'chart-key-point',
      'chart-annotation',
      'chart-conclusion',
    ];
    expect(order.every((className) => html.includes(className))).toBe(true);
    expect(html.indexOf('chart-baseline')).toBeLessThan(html.indexOf('chart-series'));
    expect(html.indexOf('chart-series')).toBeLessThan(html.indexOf('chart-key-point'));
    expect(html.indexOf('chart-key-point')).toBeLessThan(html.indexOf('chart-annotation'));
    expect(html.indexOf('chart-annotation')).toBeLessThan(html.indexOf('chart-conclusion'));
  });

  it('keeps the counter component deterministic at the same frame', () => {
    const spec = { start: 100, end: 200, durationFrames: 30, format: 'integer' as const };
    const first = renderToStaticMarkup(<StatCounter spec={spec} currentFrame={15} />);
    const second = renderToStaticMarkup(<StatCounter spec={spec} currentFrame={15} />);
    expect(first).toBe(second);
  });
});
