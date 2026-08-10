import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import { SemanticBackground } from './SemanticBackground';

describe('SemanticBackground', () => {
  it('dims the background when foreground content is active', () => {
    const idle = renderToStaticMarkup(
      <SemanticBackground preset="tech_blue" foregroundActive={false} />,
    );
    const active = renderToStaticMarkup(<SemanticBackground preset="tech_blue" foregroundActive />);
    expect(idle).toContain('background-brightness="1"');
    expect(active).toContain('background-brightness="0.72"');
  });

  it('keeps reduced motion deterministic without an infinite animation', () => {
    const html = renderToStaticMarkup(
      <SemanticBackground preset="warm_gold" foregroundActive={false} reducedMotion />,
    );
    expect(html).toContain('semantic-background');
    expect(html).not.toContain('infinite');
  });
});
