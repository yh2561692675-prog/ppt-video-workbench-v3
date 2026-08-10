import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import { CompareMode } from './CompareMode';
import { PathBuilder } from './PathBuilder';
import { RiskAlert, riskPulseFrames } from './RiskAlert';
import { TagMatrix } from './TagMatrix';

describe('semantic templates', () => {
  it('never emits more than one risk pulse', () => {
    expect(riskPulseFrames(120)).toHaveLength(1);
    expect(renderToStaticMarkup(<RiskAlert title="注意" reason="需核实条件" />)).not.toContain(
      'infinite',
    );
  });

  it('keeps both sides visible while emphasizing the narrated side', () => {
    const html = renderToStaticMarkup(<CompareMode left="优势" right="限制" active="left" />);
    expect(html).toContain('compare-mode__left');
    expect(html).toContain('compare-mode__right');
    expect(html).toContain('data-active="left"');
    expect(html).not.toContain('rotate(');
  });

  it('builds a path in reading order without repeated movement', () => {
    const html = renderToStaticMarkup(<PathBuilder nodes={['基础', '实践', '就业']} />);
    expect(html.indexOf('基础')).toBeLessThan(html.indexOf('实践'));
    expect(html.indexOf('实践')).toBeLessThan(html.indexOf('就业'));
    expect(html).not.toContain('bounce');
    expect(html).not.toContain('rotate(');
  });

  it('groups tags into readable groups of two to five', () => {
    const html = renderToStaticMarkup(
      <TagMatrix tags={['课程', '技能', '岗位', '行业', '方向', '工具']} />,
    );
    expect((html.match(/tag-matrix__group/g) ?? []).length).toBe(2);
    expect(html).not.toContain('tag-matrix__group--6');
  });
});
