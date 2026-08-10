import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';

import { AudioTimeline } from './AudioTimeline';

afterEach(() => vi.unstubAllGlobals());

it('drags a boundary with version control and supports local undo', async () => {
  const onChanged = vi.fn();
  const timeline = {
    id: 'timeline-1',
    version: 1,
    duration_ms: 3000,
    min_page_ms: 300,
    boundaries: [{ id: 'boundary-1', time_ms: 1000 }],
    segments: [
      { page_id: 'page-1', start_ms: 0, end_ms: 1000 },
      { page_id: 'page-2', start_ms: 1000, end_ms: 3000 },
    ],
  };
  vi.stubGlobal(
    'fetch',
    vi.fn(
      async () =>
        new Response(
          JSON.stringify({
            data: {
              ...timeline,
              version: 2,
              boundaries: [{ id: 'boundary-1', time_ms: 1200 }],
              segments: [
                { page_id: 'page-1', start_ms: 0, end_ms: 1200 },
                { page_id: 'page-2', start_ms: 1200, end_ms: 3000 },
              ],
            },
            error: null,
            request_id: 'request-1',
          }),
          { headers: { 'Content-Type': 'application/json' } },
        ),
    ),
  );
  render(<AudioTimeline projectId="project-1" initialTimeline={timeline} onChanged={onChanged} />);
  fireEvent.change(screen.getByLabelText('第 1 条分页线'), { target: { value: '1200' } });
  fireEvent.mouseUp(screen.getByLabelText('第 1 条分页线'));
  expect(await screen.findByText('边界已保存（版本 2）')).toBeInTheDocument();
  expect(onChanged).toHaveBeenCalledTimes(1);
  fireEvent.click(screen.getByRole('button', { name: '撤销边界调整' }));
  expect(screen.getByLabelText('第 1 条分页线')).toHaveValue('1000');
});

it('adopts a refreshed authoritative timeline', () => {
  const timeline = {
    id: 'timeline-1',
    version: 1,
    duration_ms: 3000,
    min_page_ms: 300,
    boundaries: [{ id: 'boundary-1', time_ms: 1000 }],
    segments: [
      { page_id: 'page-1', start_ms: 0, end_ms: 1000 },
      { page_id: 'page-2', start_ms: 1000, end_ms: 3000 },
    ],
  };
  const { rerender } = render(<AudioTimeline projectId="project-1" initialTimeline={timeline} />);
  rerender(
    <AudioTimeline
      projectId="project-1"
      initialTimeline={{
        ...timeline,
        version: 2,
        boundaries: [{ id: 'boundary-1', time_ms: 1500 }],
        segments: [
          { page_id: 'page-1', start_ms: 0, end_ms: 1500 },
          { page_id: 'page-2', start_ms: 1500, end_ms: 3000 },
        ],
      }}
    />,
  );

  expect(screen.getByLabelText('第 1 条分页线')).toHaveValue('1500');
});
