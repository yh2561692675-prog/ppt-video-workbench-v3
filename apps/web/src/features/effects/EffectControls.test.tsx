import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { BatchEffectStatus } from './BatchEffectStatus';
import { RhythmPanel } from './RhythmPanel';
import { TemplatePanel } from './TemplatePanel';

describe('effect controls', () => {
  it('changes rhythm profile and strength', () => {
    const onChange = vi.fn();
    render(<RhythmPanel profile="standard" strength={0.7} onChange={onChange} />);
    fireEvent.change(screen.getByLabelText('节奏档位'), { target: { value: 'compact' } });
    fireEvent.change(screen.getByLabelText('特效强度'), { target: { value: '0.9' } });
    expect(onChange).toHaveBeenNthCalledWith(1, { profile: 'compact', strength: 0.7 });
    expect(onChange).toHaveBeenNthCalledWith(2, { profile: 'standard', strength: 0.9 });
  });

  it('keeps manual lock explicit when template changes', () => {
    const onChange = vi.fn();
    render(
      <TemplatePanel
        template="ProgressiveReveal"
        background="tech_blue"
        aspectRatio="16:9"
        manualLock={false}
        onChange={onChange}
      />,
    );
    fireEvent.change(screen.getByLabelText('特效模板'), { target: { value: 'ChartNarration' } });
    fireEvent.click(screen.getByLabelText('人工锁定模板'));
    expect(onChange).toHaveBeenNthCalledWith(1, {
      template: 'ChartNarration',
      background: 'tech_blue',
      aspectRatio: '16:9',
      manualLock: false,
    });
    expect(onChange).toHaveBeenNthCalledWith(2, {
      template: 'ProgressiveReveal',
      background: 'tech_blue',
      aspectRatio: '16:9',
      manualLock: true,
    });
  });

  it('summarizes batch status and fallback count', () => {
    render(
      <BatchEffectStatus
        items={[
          { pageId: 'p1', status: 'success' },
          { pageId: 'p2', status: 'fallback' },
          { pageId: 'p3', status: 'pending' },
        ]}
      />,
    );
    expect(screen.getByRole('status')).toHaveTextContent('2/3 完成');
    expect(screen.getByText('1 页已安全降级')).toBeInTheDocument();
  });
});
