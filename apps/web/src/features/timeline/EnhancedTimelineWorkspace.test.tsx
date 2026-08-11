import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { EnhancedTimelineWorkspace } from './EnhancedTimelineWorkspace';

const tracks = [
  {
    id: 'slides',
    name: '页面',
    kind: 'slide',
    order: 0,
    clips: [
      {
        id: 'clip-1',
        kind: 'slide',
        start_us: 1_000_000,
        duration_us: 2_000_000,
        source_ref: 'page-1',
      },
    ],
  },
];

describe('EnhancedTimelineWorkspace', () => {
  it('uses server history for undo and emits frame-accurate keyboard moves', () => {
    const command = vi.fn();
    const restore = vi.fn();
    render(
      <EnhancedTimelineWorkspace
        durationUs={10_000_000}
        revision={4}
        fps={25}
        tracks={tracks}
        historyRevisions={[1, 2, 3, 4]}
        onSelectClip={vi.fn()}
        onCommand={command}
        onRestoreRevision={restore}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: /page-1/ }));
    const workspace = screen.getByRole('region', { name: '统一多轨时间线' });
    fireEvent.keyDown(workspace, { key: 'ArrowRight' });
    expect(command).toHaveBeenCalledWith({
      kind: 'move_clip',
      payload: { clip_id: 'clip-1', start_us: 1_040_000 },
    });
    fireEvent.keyDown(workspace, { key: 'z', ctrlKey: true });
    expect(restore).toHaveBeenCalledWith(3);
  });

  it('keeps a conflicting edit available for retry', () => {
    const retry = vi.fn();
    render(
      <EnhancedTimelineWorkspace
        durationUs={10_000_000}
        revision={4}
        tracks={tracks}
        conflictMessage="时间线已更新"
        onRetryConflict={retry}
        onSelectClip={vi.fn()}
        onCommand={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: '按最新版本重试' }));
    expect(retry).toHaveBeenCalledOnce();
  });
});
