import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { TimelineWorkspace } from './TimelineWorkspace';

describe('TimelineWorkspace', () => {
  it('renders ordered tracks and emits clip selection', () => {
    const onSelectClip = vi.fn();
    render(
      <TimelineWorkspace
        durationUs={10_000_000}
        revision={3}
        tracks={[
          { id: 'audio', name: '旁白', kind: 'narration', order: 1, clips: [] },
          {
            id: 'slides',
            name: '页面',
            kind: 'slide',
            order: 0,
            clips: [
              {
                id: 'clip-1',
                kind: 'slide',
                start_us: 0,
                duration_us: 2_000_000,
                source_ref: 'page-1',
              },
            ],
          },
        ]}
        onSelectClip={onSelectClip}
        onCommand={vi.fn()}
      />,
    );

    expect(screen.getByText('页面')).toBeInTheDocument();
    expect(screen.getByText('旁白')).toBeInTheDocument();
    screen.getByRole('button', { name: /page-1/ }).click();
    expect(onSelectClip).toHaveBeenCalledWith('clip-1');
  });
});
