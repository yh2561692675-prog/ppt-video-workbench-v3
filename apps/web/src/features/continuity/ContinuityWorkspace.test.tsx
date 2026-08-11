import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type { ContinuityPlanRecord } from '../../api/client';
import { ContinuityWorkspace } from './ContinuityWorkspace';

const plan: ContinuityPlanRecord = {
  version: 1,
  revision: 2,
  project_id: 'project-1',
  duration_ms: 5000,
  transitions: [
    {
      id: 'transition-1',
      from_page_id: 'page-1',
      to_page_id: 'page-2',
      kind: 'cut',
      duration_ms: 0,
      audio_mode: 'cut',
      audio_offset_ms: 0,
      easing: 'ease_in_out',
      enabled: true,
      chapter_boundary: false,
      parameters: {},
    },
  ],
  overlays: [],
  chapters: [],
  content_hash: 'a'.repeat(64),
};

describe('ContinuityWorkspace', () => {
  it('exposes transition, audio cut and overlay controls', () => {
    const onCommand = vi.fn();
    render(
      <ContinuityWorkspace
        plan={plan}
        pageLabels={{ 'page-1': '第 1 页', 'page-2': '第 2 页' }}
        onCommand={onCommand}
      />,
    );
    expect(screen.getByText(/第 1 页/)).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('转场类型'), { target: { value: 'dissolve' } });
    expect(onCommand).toHaveBeenCalledWith(expect.objectContaining({ kind: 'upsert_transition' }));
    fireEvent.click(screen.getByRole('button', { name: '添加 Logo 覆盖层' }));
    expect(onCommand).toHaveBeenCalledWith(expect.objectContaining({ kind: 'upsert_overlay' }));
  });
});
