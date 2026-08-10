import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';

import { SubtitleActions } from './SubtitleActions';

afterEach(() => vi.unstubAllGlobals());

it('builds subtitles from approved page audio and refreshes the project state', async () => {
  const onChanged = vi.fn();
  vi.stubGlobal('fetch', async (input: RequestInfo | URL) => {
    expect(String(input)).toBe('/api/projects/project-1/subtitles/build');
    return new Response(
      JSON.stringify({
        data: { version: 1, duration_ms: 1200, cues: [] },
        error: null,
        request_id: 'r1',
      }),
      { headers: { 'Content-Type': 'application/json' } },
    );
  });

  render(<SubtitleActions projectId="project-1" allowed onChanged={onChanged} />);
  fireEvent.click(screen.getByRole('button', { name: '生成字幕' }));

  expect(await screen.findByText('字幕时间轴与 SRT 已生成')).toBeInTheDocument();
  expect(onChanged).toHaveBeenCalledTimes(1);
});
