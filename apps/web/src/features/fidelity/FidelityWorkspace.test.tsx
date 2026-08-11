import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { FidelityWorkspace } from './FidelityWorkspace';

describe('FidelityWorkspace', () => {
  it('shows page fidelity level and mapped elements', () => {
    render(
      <FidelityWorkspace
        pages={[
          {
            page_id: 'page-1',
            page_index: 1,
            level: 'F2',
            renderer: 'libreoffice',
            scene: {
              shapes: [{ shape_id: 'shape-1', name: '标题', kind: 'text', text: '产品简介' }],
              motion_cues: [
                {
                  cue_id: 'cue-1',
                  shape_ids: ['shape-1'],
                  entrance: 'fade',
                  duration_ms: 500,
                  support: 'supported',
                },
              ],
            },
          },
        ]}
        onSelectPage={vi.fn()}
        onRecapture={vi.fn()}
      />,
    );

    expect(screen.getAllByText(/可解释动画/).length).toBeGreaterThan(0);
    expect(screen.getByText(/产品简介/)).toBeInTheDocument();
    expect(screen.getByText(/fade/)).toBeInTheDocument();
  });
});
